"""GitHub Update Manager (stdlib only, independent from the GIS modules and from any GUI).

Flow: check -> (user confirms) download + verify -> (user confirms) install with backup -> rollback.

Safety rules enforced here (not only in the UI)
  * only the official repository is contacted (API + release downloads; redirects are checked)
  * ``download_asset`` / ``install_update`` raise unless ``confirmed=True``
  * SHA256 is verified when a checksum is published; installing an unverified file needs
    ``allow_unverified=True``
  * archives are extracted by hand: no absolute paths, ``..``, drive letters, links or device files
  * a backup is made before anything is touched; a failure rolls everything back
  * user configuration/data is never overwritten; nothing is ever run with admin rights,
    no downloaded script is executed
"""
from __future__ import annotations

import base64
import datetime
import fnmatch
import hashlib
import json
import os
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from urllib.parse import urlparse

from tools import version as _version

REPO = _version.REPO
API_BASE = "https://api.github.com/repos/{}".format(REPO)
LATEST_URL = _version.RELEASES_API
LIST_URL = API_BASE + "/releases?per_page=15"
ALLOWED_REDIRECT_HOSTS = ("github.com", "api.github.com", "githubusercontent.com")
MAX_JSON_BYTES = 5_000_000
MAX_UNPACKED_BYTES = 4 * 1024 ** 3
MAX_FILES = 200_000
CHUNK = 64 * 1024

# Ed25519 public key (base64) used to verify a signed checksum manifest (``SHA256SUMS`` + ``SHA256SUMS.sig``).
# Empty = signature checking not configured yet (releases are then reported as "unsigned").
PUBLIC_KEY_B64 = ""

# Top-level names (fnmatch) that belong to the user and are never overwritten by an update.
PRESERVE = ("config.txt", "gis_box_settings.json", "GIS_BOX_config", "shp_coords_templates.txt",
            "map_services.txt", "gdb2postgis_audit.db", "gdb2postgis_run.log", "logs", "db_transfer_logs",
            ".venv", "*.mdb")
BACKUP_IGNORE = (".git", ".venv", "__pycache__", "build", "dist", "logs", "db_transfer_logs", "*.pyc")


class UpdateError(Exception):
    """``code``: network, rate_limit, http, bad_json, bad_version, not_official, unsafe_redirect,
    no_asset, confirmation_required, checksum, size, cancelled, unsafe_archive, bad_package,
    git_checkout, locked, unverified, signature, signature_unsupported, no_backup."""

    def __init__(self, code, detail=""):
        super().__init__("{}: {}".format(code, detail) if detail else code)
        self.code = code
        self.detail = detail


# ----------------------------------------------------------------------------- URL rules
def _host_ok(host):
    host = (host or "").lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_REDIRECT_HOSTS)


def is_official_api_url(url):
    u = urlparse(url)
    return (u.scheme == "https" and u.hostname == "api.github.com"
            and u.path.lower().startswith("/repos/{}/".format(REPO.lower())))


def is_official_download_url(url):
    u = urlparse(url)
    if u.scheme != "https":
        return False
    p = u.path.lower()
    if u.hostname == "github.com":
        return p.startswith("/{}/releases/download/".format(REPO.lower()))
    return is_official_api_url(url)                    # API asset endpoints


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlparse(newurl)
        if u.scheme != "https" or not _host_ok(u.hostname):
            raise UpdateError("unsafe_redirect", newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_opener(url, headers=None, timeout=25):
    """urllib opener with checked redirects and a generic User-Agent (no personal data)."""
    h = {"User-Agent": "GIS_BOX-updater/{}".format(_version.__version__), "Accept": "application/vnd.github+json"}
    h.update(headers or {})
    op = urllib.request.build_opener(_SafeRedirect)
    return op.open(urllib.request.Request(url, headers=h), timeout=timeout)


def _open(url, opener=None, headers=None):
    """Open ``url`` with unified error mapping."""
    try:
        return (opener or default_opener)(url, headers=headers)
    except UpdateError:
        raise
    except urllib.error.HTTPError as e:
        remaining = e.headers.get("X-RateLimit-Remaining") if e.headers else None
        if e.code in (403, 429) and (remaining == "0" or e.code == 429):
            raise UpdateError("rate_limit", "GitHub API rate limit reached - try again later") from e
        raise UpdateError("http", "HTTP {} {}".format(e.code, e.reason)) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError("network", str(getattr(e, "reason", e))) from e


def _read_limited(resp, limit):
    data = resp.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("http", "response too large")
    return data


def get_json(url, opener=None):
    if not is_official_api_url(url):
        raise UpdateError("not_official", url)
    resp = _open(url, opener)
    try:
        return json.loads(_read_limited(resp, MAX_JSON_BYTES).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise UpdateError("bad_json", str(e)) from e
    finally:
        _close(resp)


def _close(resp):
    try:
        resp.close()
    except Exception:                                   # noqa: BLE001
        pass


# ----------------------------------------------------------------------------- releases
@dataclass
class Asset:
    name: str
    url: str
    size: int = 0
    digest: str = ""            # sha256 hex given by the GitHub API (if any)

    @property
    def installable(self):
        n = self.name.lower()
        return n.endswith((".zip", ".tar.gz", ".tgz"))


@dataclass
class Release:
    tag: str
    version: str
    name: str = ""
    notes: str = ""
    published: str = ""
    prerelease: bool = False
    assets: list = field(default_factory=list)


def parse_release(d):
    if not isinstance(d, dict):
        raise UpdateError("bad_json", "release is not an object")
    tag = str(d.get("tag_name") or "")
    try:
        _version.parse(tag)
    except ValueError as e:
        raise UpdateError("bad_version", tag) from e
    assets = []
    for a in d.get("assets") or []:
        url = a.get("browser_download_url") or ""
        name = os.path.basename(str(a.get("name") or ""))
        if not name or not is_official_download_url(url):
            continue                                     # foreign/unsafe assets are ignored entirely
        dg = str(a.get("digest") or "")
        assets.append(Asset(name, url, int(a.get("size") or 0),
                            dg.split(":", 1)[1].lower() if dg.lower().startswith("sha256:") else ""))
    return Release(tag=tag, version=tag.lstrip("vV"), name=str(d.get("name") or tag),
                   notes=str(d.get("body") or ""), published=str(d.get("published_at") or ""),
                   prerelease=bool(d.get("prerelease")), assets=assets)


def fetch_latest(allow_prerelease=False, opener=None):
    """Latest stable release (``/releases/latest``) or, with prereleases allowed, the highest version."""
    if not allow_prerelease:
        return parse_release(get_json(LATEST_URL, opener))
    items = get_json(LIST_URL, opener)
    if not isinstance(items, list):
        raise UpdateError("bad_json", "release list expected")
    best = None
    for it in items:
        if not isinstance(it, dict) or it.get("draft"):
            continue
        try:
            r = parse_release(it)
        except UpdateError:
            continue
        key = (_version.parse(r.tag)[0], not r.prerelease)
        if best is None or key > best[0]:
            best = (key, r)
    if best is None:
        raise UpdateError("no_asset", "no usable release found")
    return best[1]


@dataclass
class UpdateCheck:
    status: str                  # available | up_to_date | error
    current: str
    latest: Release | None = None
    error: UpdateError | None = None
    checked_at: str = ""


def check_for_updates(current=None, allow_prerelease=False, opener=None):
    """Never raises: network/API problems come back as ``status == "error"``. Never downloads anything."""
    current = current or _version.__version__
    now = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        rel = fetch_latest(allow_prerelease, opener)
    except UpdateError as e:
        return UpdateCheck("error", current, None, e, now)
    status = "available" if _version.is_newer(rel.tag, current) else "up_to_date"
    return UpdateCheck(status, current, rel, None, now)


def should_auto_check(last_check, now=None, interval_hours=24):
    if not last_check:
        return True
    try:
        last = datetime.datetime.fromisoformat(last_check)
    except ValueError:
        return True
    return ((now or datetime.datetime.now()) - last).total_seconds() >= interval_hours * 3600


# ----------------------------------------------------------------------------- asset selection
def select_asset(release, system=None, machine=None):
    """Pick the right official asset for this OS: Windows x64 ZIP; Linux TAR.GZ, then AppImage, then DEB."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    arm = any(x in machine for x in ("arm", "aarch"))
    cands = [a for a in release.assets
             if not a.name.lower().endswith((".sha256", ".sha256sum", ".sig", ".txt", ".asc", ".md5"))]

    def has(a, *words):
        return any(w in a.name.lower() for w in words)

    if system == "windows":
        if arm:
            return None
        zips = [a for a in cands if a.name.lower().endswith(".zip") and has(a, "win")]
        zips.sort(key=lambda a: (not has(a, "x64", "amd64", "win64"), a.name))
        return zips[0] if zips else None
    if system == "linux":
        for ext in (".tar.gz", ".tgz", ".appimage", ".deb"):
            hit = [a for a in cands if a.name.lower().endswith(ext) and has(a, "linux", "ubuntu", "debian", "amd64", "x86_64", "x64", "appimage")
                   and (arm == has(a, "arm", "aarch"))]
            if ext == ".deb":
                hit = [a for a in hit if has(a, "amd64", "x64", "x86_64", "linux")] if not arm else hit
            if hit:
                return sorted(hit, key=lambda a: a.name)[0]
    return None


# ----------------------------------------------------------------------------- checksums / signatures
def parse_checksums(text):
    """``{filename: sha256}`` from ``sha256sum`` style text (``<hash>  name`` / ``<hash> *name``)."""
    out = {}
    for line in (text or "").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64 and all(c in "0123456789abcdefABCDEF" for c in parts[0]):
            out[os.path.basename(parts[1].lstrip("*").strip())] = parts[0].lower()
        elif len(parts) == 1 and len(parts[0]) == 64:
            out[""] = parts[0].lower()               # single-hash file
    return out


def verify_signature(data, signature_b64, public_key_b64):
    """Ed25519 verification of a signed manifest. Raises ``UpdateError('signature')`` on failure."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as e:
        raise UpdateError("signature_unsupported", "pip install cryptography") from e
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        key.verify(base64.b64decode(signature_b64.strip()), data)
    except (InvalidSignature, ValueError) as e:
        raise UpdateError("signature", "signature does not match") from e
    return True


@dataclass
class Checksum:
    sha256: str = ""
    source: str = ""             # api-digest | <file name> | ""
    signed: bool = False         # manifest signature verified


def _fetch_text(asset, opener):
    resp = _open(asset.url, opener, headers={"Accept": "application/octet-stream"})
    try:
        return _read_limited(resp, 1_000_000)
    finally:
        _close(resp)


def find_checksum(release, asset, opener=None, public_key_b64=None):
    """SHA256 for ``asset``: API digest, ``<asset>.sha256`` or a ``SHA256SUMS``-style manifest.
    A manifest with a ``.sig`` is signature-checked when a public key is configured."""
    key = PUBLIC_KEY_B64 if public_key_b64 is None else public_key_b64
    if asset.digest:
        return Checksum(asset.digest, "api-digest")
    by_name = {a.name.lower(): a for a in release.assets}
    for cand in (asset.name + ".sha256", asset.name + ".sha256sum", "sha256sums", "sha256sums.txt", "checksums.txt"):
        a = by_name.get(cand.lower())
        if not a:
            continue
        raw = _fetch_text(a, opener)
        sums = parse_checksums(raw.decode("utf-8", "replace"))
        h = sums.get(asset.name) or sums.get("")
        if not h:
            continue
        signed = False
        sig = by_name.get(a.name.lower() + ".sig")
        if sig and key:
            verify_signature(raw, _fetch_text(sig, opener).decode("ascii", "ignore"), key)
            signed = True
        return Checksum(h, a.name, signed)
    return Checksum()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------- download
@dataclass
class DownloadResult:
    path: str
    sha256: str
    verified: bool               # True only if a published checksum matched
    checksum_source: str = ""
    signed: bool = False


def download_asset(asset, dest_dir, checksum=None, confirmed=False, progress=None, cancel=None, opener=None):
    """Download ``asset`` into ``dest_dir`` (via ``.part`` file; a partial/failed download never remains)."""
    if not confirmed:
        raise UpdateError("confirmation_required", "downloading needs the user's consent")
    if not is_official_download_url(asset.url):
        raise UpdateError("not_official", asset.url)
    name = os.path.basename(asset.name)
    if not name or name != asset.name or name in (".", ".."):
        raise UpdateError("unsafe_archive", asset.name)
    os.makedirs(dest_dir, exist_ok=True)
    final = os.path.join(dest_dir, name)
    part = final + ".part"
    resp = _open(asset.url, opener, headers={"Accept": "application/octet-stream"})
    h = hashlib.sha256()
    done = 0
    try:
        total = int((getattr(resp, "headers", {}) or {}).get("Content-Length") or asset.size or 0)
        with open(part, "wb") as f:
            while True:
                if cancel and cancel():
                    raise UpdateError("cancelled")
                try:
                    chunk = resp.read(CHUNK)
                except (OSError, TimeoutError) as e:          # connection dropped mid-download
                    raise UpdateError("network", str(e)) from e
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if (asset.size and done != asset.size) or (total and done != total):
            raise UpdateError("size", "got {} bytes, expected {}".format(done, asset.size or total))
        digest = h.hexdigest()
        want = (checksum.sha256 if checksum else "").lower()
        if want and digest != want:
            raise UpdateError("checksum", "SHA256 mismatch (expected {}, got {})".format(want, digest))
        os.replace(part, final)
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    finally:
        _close(resp)
    return DownloadResult(final, digest, bool(want), checksum.source if checksum else "",
                          bool(checksum and checksum.signed))


# ----------------------------------------------------------------------------- safe extraction
def _safe_rel(name):
    n = name.replace("\\", "/")
    if not n or n.startswith("/") or (len(n) > 1 and n[1] == ":") or n.startswith("//"):
        raise UpdateError("unsafe_archive", name)
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts) or any("\x00" in p for p in parts):
        raise UpdateError("unsafe_archive", name)
    return "/".join(parts)


def _target(dest, rel):
    root = os.path.realpath(dest)
    t = os.path.realpath(os.path.join(root, *rel.split("/")))
    if t != root and not t.startswith(root + os.sep):
        raise UpdateError("unsafe_archive", rel)
    return t


def safe_extract(archive, dest):
    """Extract ``.zip`` / ``.tar.gz`` into ``dest`` refusing path traversal, links, devices and bombs.
    Returns the list of extracted file paths (relative, ``/``-separated)."""
    os.makedirs(dest, exist_ok=True)
    files, total = [], 0
    low = archive.lower()
    if low.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            if len(infos) > MAX_FILES:
                raise UpdateError("unsafe_archive", "too many files")
            for info in infos:
                mode = (info.external_attr >> 16) & 0o170000
                if mode in (stat.S_IFLNK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK):
                    raise UpdateError("unsafe_archive", "link/device entry: " + info.filename)
                rel = _safe_rel(info.filename)
                t = _target(dest, rel)
                if info.is_dir():
                    os.makedirs(t, exist_ok=True)
                    continue
                total += info.file_size
                if total > MAX_UNPACKED_BYTES:
                    raise UpdateError("unsafe_archive", "unpacked size limit exceeded")
                os.makedirs(os.path.dirname(t), exist_ok=True)
                with z.open(info) as src, open(t, "wb") as out:
                    shutil.copyfileobj(src, out)
                files.append(rel)
    elif low.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive, "r:gz") as tf:
            n = 0
            for m in tf:
                n += 1
                if n > MAX_FILES:
                    raise UpdateError("unsafe_archive", "too many files")
                if m.issym() or m.islnk() or m.isdev() or m.isfifo():
                    raise UpdateError("unsafe_archive", "link/device entry: " + m.name)
                rel = _safe_rel(m.name)
                t = _target(dest, rel)
                if m.isdir():
                    os.makedirs(t, exist_ok=True)
                    continue
                if not m.isfile():
                    raise UpdateError("unsafe_archive", m.name)
                total += m.size
                if total > MAX_UNPACKED_BYTES:
                    raise UpdateError("unsafe_archive", "unpacked size limit exceeded")
                os.makedirs(os.path.dirname(t), exist_ok=True)
                src = tf.extractfile(m)
                with open(t, "wb") as out:
                    shutil.copyfileobj(src, out)
                if m.mode & 0o111:                         # keep the executable bit (Linux binary)
                    os.chmod(t, 0o755)
                files.append(rel)
    else:
        raise UpdateError("bad_package", "unsupported archive type: " + os.path.basename(archive))
    return files


MARKERS = ("GIS_BOX.exe", "GIS_BOX", "gis_box.py")


def find_content_root(staging):
    """The folder that holds the application (descends into a single top-level directory)."""
    root = staging
    for _ in range(2):
        entries = os.listdir(root)
        if len(entries) == 1 and os.path.isdir(os.path.join(root, entries[0])):
            root = os.path.join(root, entries[0])
        else:
            break
    if not any(os.path.exists(os.path.join(root, m)) for m in MARKERS):
        raise UpdateError("bad_package", "no GIS_BOX application found in the package")
    return root


# ----------------------------------------------------------------------------- install / rollback
def is_preserved(rel, patterns=PRESERVE):
    top = rel.split("/")[0]
    return any(fnmatch.fnmatch(top, p) or fnmatch.fnmatch(rel, p) for p in patterns)


def default_app_dir():
    import sys
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class InstallResult:
    backup_dir: str
    replaced: list
    added: list
    skipped: list
    version: str = ""


def _ts():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


OLD_MARK = ".gbold-"      # a replaced-but-still-locked file is renamed to <name>.gbold-<n> until the next start


def _place(tmp, dst):
    """``os.replace(tmp, dst)``; on Windows a file that is in use (the running ``GIS_BOX.exe``, loaded DLLs/pyd)
    cannot be overwritten but CAN be renamed: it is renamed away, the new file takes its name, and the old copy
    is deleted by :func:`cleanup_old_files` at the next start. Raises ``PermissionError`` when even that fails."""
    try:
        os.replace(tmp, dst)
        return
    except PermissionError as first:
        if os.name != "nt" or not os.path.exists(dst):
            raise
        old = "{}{}{}".format(dst, OLD_MARK, int(datetime.datetime.now().timestamp() * 1000))
        try:
            os.replace(dst, old)                      # rename away (allowed for files in use)
        except OSError:
            raise first
        try:
            os.replace(tmp, dst)
        except OSError:
            try:
                os.replace(old, dst)                  # put the original back - never leave the app without the file
            except OSError:
                pass
            raise


def cleanup_on_start():
    """Start-up hook of an INSTALLED (frozen) build: remove leftovers of a previous update in a background thread.
    Does nothing when running from source."""
    import sys
    import threading
    if not getattr(sys, "frozen", False):
        return None
    t = threading.Thread(target=lambda: cleanup_old_files(default_app_dir()), name="gisbox-update-cleanup", daemon=True)
    t.start()
    return t


def cleanup_old_files(app_dir):
    """Delete the ``*.gbold-*`` leftovers of a previous update (best effort; skips dev/venv folders).
    Returns how many were removed. Call once at start-up of an installed (frozen) build."""
    removed = 0
    for dp, dn, fn in os.walk(app_dir):
        dn[:] = [d for d in dn if d not in (".git", ".venv", "node_modules", "__pycache__")]
        for f in fn:
            if OLD_MARK in f:
                try:
                    os.remove(os.path.join(dp, f))
                    removed += 1
                except OSError:
                    pass                               # still in use - next start
    return removed


def install_update(archive, app_dir, backup_root, new_version="", confirmed=False, allow_unverified=False,
                   verified=False, preserve=PRESERVE, progress=None, log=None):
    """Extract -> backup -> apply -> (on any failure) rollback. Needs ``confirmed=True``.

    ``verified`` must be the ``DownloadResult.verified`` flag; an unverified package is refused
    unless ``allow_unverified=True``. A git checkout (developer copy) is never overwritten."""
    log = log or (lambda _m: None)
    if not confirmed:
        raise UpdateError("confirmation_required", "installing needs the user's consent")
    if not (verified or allow_unverified):
        raise UpdateError("unverified", "no matching SHA256 checksum - refusing to install")
    if os.path.isdir(os.path.join(app_dir, ".git")):
        raise UpdateError("git_checkout", "this is a git checkout - update with 'git pull' instead")
    os.makedirs(backup_root, exist_ok=True)
    stamp = _ts()
    staging = tempfile.mkdtemp(prefix=".staging_" + stamp + "_", dir=backup_root)
    backup = None
    replaced, added, skipped = [], [], []
    try:
        log("extracting {}".format(os.path.basename(archive)))
        safe_extract(archive, staging)
        root = find_content_root(staging)
        staged = []
        for dp, _dn, fn in os.walk(root):
            for f in fn:
                staged.append(os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/"))
        staged.sort()
        cur_ver = _current_version_text()
        backup = os.path.join(backup_root, "{}_{}".format(cur_ver, stamp))
        log("backup of the current application -> {}".format(backup))
        shutil.copytree(app_dir, backup, ignore=shutil.ignore_patterns(*BACKUP_IGNORE), dirs_exist_ok=False)
        n = len(staged)
        try:
            for i, rel in enumerate(staged, 1):
                if is_preserved(rel, preserve):
                    skipped.append(rel)
                    continue
                dst = os.path.join(app_dir, *rel.split("/"))
                existed = os.path.exists(dst)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                tmp = dst + ".gbupd"
                shutil.copy2(os.path.join(root, *rel.split("/")), tmp)
                try:
                    _place(tmp, dst)
                except PermissionError as e:
                    _silent_remove(tmp)
                    raise UpdateError("locked", "{} is in use - close GIS_BOX and try again".format(rel)) from e
                (replaced if existed else added).append(rel)
                if progress:
                    progress(i, n)
        except BaseException:
            log("update failed - rolling back")
            failed = _undo(app_dir, backup, replaced, added)
            if failed:
                log("WARNING: could not restore: {}".format(", ".join(failed[:10])))
            raise
        manifest = {"version_before": cur_ver, "version_after": new_version, "time": stamp,
                    "replaced": replaced, "added": added, "skipped": skipped, "app_dir": app_dir}
        with open(os.path.join(backup, ".update_manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=1)
        log("update applied: {} replaced, {} added, {} user files preserved".format(
            len(replaced), len(added), len(skipped)))
        return InstallResult(backup, replaced, added, skipped, new_version)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _current_version_text():
    return _version.__version__


def _silent_remove(p):
    try:
        os.remove(p)
    except OSError:
        pass


def _undo(app_dir, backup, replaced, added):
    """Restore replaced files / remove added ones. Returns the list of files that could not be restored."""
    failed = []
    for rel in replaced:
        src = os.path.join(backup, *rel.split("/"))
        dst = os.path.join(app_dir, *rel.split("/"))
        tmp = dst + ".gbupd"
        try:
            if os.path.exists(src):
                shutil.copy2(src, tmp)
                _place(tmp, dst)
        except OSError:
            _silent_remove(tmp)
            failed.append(rel)
    for rel in added:
        _silent_remove(os.path.join(app_dir, *rel.split("/")))
    return failed


def list_backups(backup_root):
    """Backups that contain an update manifest, newest first."""
    out = []
    if not os.path.isdir(backup_root):
        return out
    for d in sorted(os.listdir(backup_root), reverse=True):
        mp = os.path.join(backup_root, d, ".update_manifest.json")
        if os.path.isfile(mp):
            try:
                with open(mp, encoding="utf-8") as f:
                    out.append({"dir": os.path.join(backup_root, d), **json.load(f)})
            except (OSError, ValueError):
                pass
    return out


def rollback_update(backup_dir, confirmed=False):
    """Restore the files an update replaced and remove the files it added (needs ``confirmed=True``)."""
    if not confirmed:
        raise UpdateError("confirmation_required", "rollback needs the user's consent")
    mp = os.path.join(backup_dir, ".update_manifest.json")
    if not os.path.isfile(mp):
        raise UpdateError("no_backup", backup_dir)
    with open(mp, encoding="utf-8") as f:
        m = json.load(f)
    app_dir = m["app_dir"]
    failed = _undo(app_dir, backup_dir, m["replaced"], m["added"])
    if failed:
        raise UpdateError("locked", "could not restore: {}".format(", ".join(failed[:10])))
    return m


def prune_backups(backup_root, keep=3):
    """Keep the newest ``keep`` backups, delete older ones. Returns the number removed."""
    olds = list_backups(backup_root)[keep:]
    for b in olds:
        shutil.rmtree(b["dir"], ignore_errors=True)
    return len(olds)
