import base64
import hashlib
import io
import json
import os
import tarfile
import urllib.error
import zipfile

import pytest

from tools import update_manager as um
from tools import version

REPO = version.REPO
API = "https://api.github.com/repos/{}".format(REPO)
DL = "https://github.com/{}/releases/download".format(REPO)


# ----------------------------------------------------------------------------- fakes
class Resp:
    def __init__(self, data, headers=None):
        self._b = io.BytesIO(data)
        self.headers = headers or {"Content-Length": str(len(data))}

    def read(self, n=-1):
        return self._b.read(n)

    def close(self):
        pass


class Net:
    """Fake opener: url -> bytes | Exception."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, headers=None):
        self.calls.append(url)
        v = self.routes.get(url)
        if v is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        if isinstance(v, Exception):
            raise v
        return Resp(v)


def rel_json(tag="v2.1.0", prerelease=False, assets=(), draft=False):
    return {"tag_name": tag, "name": tag, "body": "notes of " + tag, "published_at": "2026-01-02T03:04:05Z",
            "prerelease": prerelease, "draft": draft,
            "assets": [{"name": n, "size": s, "browser_download_url": u, **({"digest": d} if d else {})}
                       for n, s, u, d in assets]}


def j(o):
    return json.dumps(o).encode()


def make_zip(path, files, top=None):
    with zipfile.ZipFile(path, "w") as z:
        for n, data in files.items():
            z.writestr((top + "/" if top else "") + n, data)
    return path


# ----------------------------------------------------------------------------- URL rules / releases
def test_official_url_rules():
    assert um.is_official_api_url(API + "/releases/latest")
    assert not um.is_official_api_url("https://api.github.com/repos/evil/x/releases/latest")
    assert not um.is_official_api_url("http://api.github.com/repos/{}/releases".format(REPO))
    assert um.is_official_download_url(DL + "/v1/a.zip")
    assert not um.is_official_download_url("https://github.com/evil/x/releases/download/v1/a.zip")
    assert not um.is_official_download_url("https://evil.com/{}/releases/download/v1/a.zip".format(REPO))


def test_parse_release_drops_foreign_assets_and_bad_tags():
    r = um.parse_release(rel_json(assets=[("ok.zip", 5, DL + "/v2.1.0/ok.zip", ""),
                                          ("bad.zip", 5, "https://evil.com/bad.zip", "")]))
    assert [a.name for a in r.assets] == ["ok.zip"] and r.version == "2.1.0" and r.published.startswith("2026")
    with pytest.raises(um.UpdateError) as e:
        um.parse_release(rel_json(tag="nightly"))
    assert e.value.code == "bad_version"


def test_api_digest_is_read():
    r = um.parse_release(rel_json(assets=[("a.zip", 1, DL + "/v2.1.0/a.zip", "sha256:" + "AB" * 32)]))
    assert r.assets[0].digest == "ab" * 32


def test_check_available_up_to_date_and_error():
    net = Net({um.LATEST_URL: j(rel_json("v2.1.0"))})
    c = um.check_for_updates("2.0.0", opener=net)
    assert c.status == "available" and c.latest.version == "2.1.0" and c.checked_at
    assert um.check_for_updates("2.1.0", opener=net).status == "up_to_date"
    assert um.check_for_updates("3.0.0", opener=net).status == "up_to_date"
    # release beats its own prerelease
    assert um.check_for_updates("2.1.0-rc.1", opener=net).status == "available"


def test_check_never_raises_and_maps_errors():
    e = um.check_for_updates("2.0.0", opener=Net({um.LATEST_URL: urllib.error.URLError("offline")}))
    assert e.status == "error" and e.error.code == "network"
    h = urllib.error.HTTPError(um.LATEST_URL, 403, "rate limited", {"X-RateLimit-Remaining": "0"}, None)
    assert um.check_for_updates("2.0.0", opener=Net({um.LATEST_URL: h})).error.code == "rate_limit"
    assert um.check_for_updates("2.0.0", opener=Net({})).error.code == "http"
    assert um.check_for_updates("2.0.0", opener=Net({um.LATEST_URL: b"<html>"})).error.code == "bad_json"
    assert um.check_for_updates("2.0.0", opener=Net({um.LATEST_URL: j(rel_json("weird"))})).error.code == "bad_version"
    assert um.check_for_updates("2.0.0", opener=Net({um.LATEST_URL: TimeoutError("slow")})).error.code == "network"


def test_prerelease_selection():
    items = [rel_json("v2.2.0-rc.1", True), rel_json("v2.1.0"), rel_json("v9.9.9", draft=True), rel_json("bad")]
    net = Net({um.LIST_URL: j(items), um.LATEST_URL: j(rel_json("v2.1.0"))})
    assert um.fetch_latest(False, net).tag == "v2.1.0"
    assert um.fetch_latest(True, net).tag == "v2.2.0-rc.1"      # drafts and bad tags are skipped
    net2 = Net({um.LIST_URL: j([rel_json("v2.1.0"), rel_json("v2.1.0-rc.1", True)])})
    assert um.fetch_latest(True, net2).tag == "v2.1.0"          # a release beats its own rc


def test_foreign_api_url_never_fetched():
    net = Net({})
    with pytest.raises(um.UpdateError) as e:
        um.get_json("https://evil.com/x", net)
    assert e.value.code == "not_official" and net.calls == []


def test_redirect_to_foreign_host_is_refused():
    h = um._SafeRedirect()
    with pytest.raises(um.UpdateError) as e:
        h.redirect_request(None, None, 302, "Found", {}, "https://evil.com/a.zip")
    assert e.value.code == "unsafe_redirect"
    with pytest.raises(um.UpdateError):
        h.redirect_request(None, None, 302, "Found", {}, "http://objects.githubusercontent.com/a.zip")


def test_should_auto_check():
    import datetime as dt
    now = dt.datetime(2026, 5, 2, 12, 0, 0)
    assert um.should_auto_check("", now) and um.should_auto_check("garbage", now)
    assert not um.should_auto_check("2026-05-02T01:00:00", now)
    assert um.should_auto_check("2026-05-01T11:00:00", now)


# ----------------------------------------------------------------------------- asset selection
def _rel(*names):
    return um.Release("v2.1.0", "2.1.0", assets=[um.Asset(n, DL + "/v2.1.0/" + n) for n in names])


def test_select_asset_per_platform():
    r = _rel("GIS_BOX-windows-x64.zip", "GIS_BOX-linux-x64.tar.gz", "gis-box_2.1.0_amd64.deb",
             "GIS_BOX-x86_64.AppImage", "GIS_BOX-windows-x64.zip.sha256", "SHA256SUMS")
    assert um.select_asset(r, "Windows", "AMD64").name == "GIS_BOX-windows-x64.zip"
    assert um.select_asset(r, "Linux", "x86_64").name == "GIS_BOX-linux-x64.tar.gz"
    assert um.select_asset(_rel("gis-box_2.1.0_amd64.deb", "GIS_BOX-x86_64.AppImage"), "Linux", "x86_64").name.endswith("AppImage")
    assert um.select_asset(_rel("gis-box_2.1.0_amd64.deb"), "Linux", "x86_64").name.endswith(".deb")
    assert um.select_asset(r, "Darwin", "arm64") is None
    assert um.select_asset(r, "Linux", "aarch64") is None           # no arm build published
    assert um.select_asset(r, "Windows", "ARM64") is None
    assert um.Asset("a.zip", "u").installable and not um.Asset("a.deb", "u").installable


# ----------------------------------------------------------------------------- checksums / signatures
def test_parse_checksums():
    h = "a" * 64
    assert um.parse_checksums("{}  one.zip\n{} *two.tar.gz\n".format(h, h.upper())) == {"one.zip": h, "two.tar.gz": h.upper().lower()}
    assert um.parse_checksums(h + "\n") == {"": h}
    assert um.parse_checksums("garbage") == {}


def test_find_checksum_sources():
    h = "b" * 64
    a = um.Asset("pkg.zip", DL + "/v/pkg.zip", 3, digest=h)
    assert um.find_checksum(_rel(), a).source == "api-digest"
    rel = _rel("pkg.zip", "pkg.zip.sha256")
    net = Net({DL + "/v2.1.0/pkg.zip.sha256": (h + "  pkg.zip\n").encode()})
    c = um.find_checksum(rel, rel.assets[0], net)
    assert c.sha256 == h and c.source == "pkg.zip.sha256" and not c.signed
    rel = _rel("pkg.zip", "SHA256SUMS")
    net = Net({DL + "/v2.1.0/SHA256SUMS": "{}  other.zip\n{}  pkg.zip\n".format("c" * 64, h).encode()})
    assert um.find_checksum(rel, rel.assets[0], net).sha256 == h
    assert um.find_checksum(_rel("pkg.zip"), um.Asset("pkg.zip", "u")).sha256 == ""


def test_signed_manifest_verification_and_tamper():
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    sk = Ed25519PrivateKey.generate()
    pub = base64.b64encode(sk.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    h = "d" * 64
    manifest = "{}  pkg.zip\n".format(h).encode()
    sig = base64.b64encode(sk.sign(manifest)).decode()
    rel = _rel("pkg.zip", "SHA256SUMS", "SHA256SUMS.sig")
    base = DL + "/v2.1.0/"
    net = Net({base + "SHA256SUMS": manifest, base + "SHA256SUMS.sig": sig.encode()})
    c = um.find_checksum(rel, rel.assets[0], net, public_key_b64=pub)
    assert c.sha256 == h and c.signed
    bad = Net({base + "SHA256SUMS": manifest.replace(b"d", b"e"), base + "SHA256SUMS.sig": sig.encode()})
    with pytest.raises(um.UpdateError) as e:
        um.find_checksum(rel, rel.assets[0], bad, public_key_b64=pub)
    assert e.value.code == "signature"
    # no key configured -> manifest is used but reported as unsigned
    assert not um.find_checksum(rel, rel.assets[0], net, public_key_b64="").signed


# ----------------------------------------------------------------------------- download
def _asset(data, name="pkg.zip", size=None):
    return um.Asset(name, "{}/v2.1.0/{}".format(DL, name), len(data) if size is None else size), {
        "{}/v2.1.0/{}".format(DL, name): data}


def test_download_requires_confirmation(tmp_path):
    a, routes = _asset(b"abc")
    with pytest.raises(um.UpdateError) as e:
        um.download_asset(a, str(tmp_path), opener=Net(routes))
    assert e.value.code == "confirmation_required" and not os.listdir(tmp_path)


def test_download_ok_with_verified_checksum_and_progress(tmp_path):
    data = os.urandom(200_000)
    a, routes = _asset(data)
    seen = []
    cs = um.Checksum(hashlib.sha256(data).hexdigest(), "api-digest")
    r = um.download_asset(a, str(tmp_path), cs, confirmed=True, progress=lambda d, t: seen.append((d, t)),
                          opener=Net(routes))
    assert r.verified and r.sha256 == cs.sha256 and open(r.path, "rb").read() == data
    assert seen[-1] == (len(data), len(data)) and not any(n.endswith(".part") for n in os.listdir(tmp_path))


def test_download_unverified_when_no_checksum(tmp_path):
    a, routes = _asset(b"hello")
    r = um.download_asset(a, str(tmp_path), None, confirmed=True, opener=Net(routes))
    assert not r.verified and r.sha256 == hashlib.sha256(b"hello").hexdigest()


def test_download_checksum_mismatch_leaves_nothing(tmp_path):
    a, routes = _asset(b"hello")
    with pytest.raises(um.UpdateError) as e:
        um.download_asset(a, str(tmp_path), um.Checksum("0" * 64, "x"), confirmed=True, opener=Net(routes))
    assert e.value.code == "checksum" and os.listdir(tmp_path) == []


def test_download_size_mismatch_and_interrupted(tmp_path):
    a, routes = _asset(b"hello", size=999)
    with pytest.raises(um.UpdateError) as e:
        um.download_asset(a, str(tmp_path), None, confirmed=True, opener=Net(routes))
    assert e.value.code == "size" and os.listdir(tmp_path) == []
    a, routes = _asset(b"x" * 300_000)
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 2
    with pytest.raises(um.UpdateError) as e:
        um.download_asset(a, str(tmp_path), None, confirmed=True, cancel=cancel, opener=Net(routes))
    assert e.value.code == "cancelled" and os.listdir(tmp_path) == []


def test_download_refuses_unofficial_url_and_odd_names(tmp_path):
    net = Net({})
    with pytest.raises(um.UpdateError) as e:
        um.download_asset(um.Asset("a.zip", "https://evil.com/a.zip"), str(tmp_path), confirmed=True, opener=net)
    assert e.value.code == "not_official" and net.calls == []
    with pytest.raises(um.UpdateError):
        um.download_asset(um.Asset("../a.zip", DL + "/v/a.zip"), str(tmp_path), confirmed=True, opener=net)


def test_download_network_failure_midway(tmp_path):
    class Broken(Resp):
        def read(self, n=-1):
            raise OSError("connection reset")
    a, _ = _asset(b"abc")
    with pytest.raises(um.UpdateError) as e:
        um.download_asset(a, str(tmp_path), None, confirmed=True, opener=lambda u, headers=None: Broken(b"x"))
    assert e.value.code == "network" and os.listdir(tmp_path) == []


# ----------------------------------------------------------------------------- safe extraction
def test_zip_extraction_ok(tmp_path):
    z = make_zip(str(tmp_path / "a.zip"), {"GIS_BOX.exe": b"x", "lib/a.dll": b"y"})
    files = um.safe_extract(z, str(tmp_path / "out"))
    assert sorted(files) == ["GIS_BOX.exe", "lib/a.dll"] and (tmp_path / "out" / "lib" / "a.dll").read_bytes() == b"y"


@pytest.mark.parametrize("evil", ["../evil.txt", "a/../../evil.txt", "/abs.txt", "C:/win.txt", "..\\evil.txt", "\\\\srv\\x"])
def test_zip_path_traversal_rejected(tmp_path, evil):
    z = str(tmp_path / "e.zip")
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr(evil, "boom")
    with pytest.raises(um.UpdateError) as e:
        um.safe_extract(z, str(tmp_path / "out"))
    assert e.value.code == "unsafe_archive"
    assert not (tmp_path / "evil.txt").exists()


def test_zip_symlink_rejected(tmp_path):
    z = str(tmp_path / "l.zip")
    with zipfile.ZipFile(z, "w") as zf:
        info = zipfile.ZipInfo("link")
        info.external_attr = (0o120777 << 16)
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(um.UpdateError):
        um.safe_extract(z, str(tmp_path / "out"))


def _tar(path, members):
    with tarfile.open(path, "w:gz") as tf:
        for name, kind, data in members:
            ti = tarfile.TarInfo(name)
            if kind == "file":
                ti.size = len(data)
                ti.mode = 0o755
                tf.addfile(ti, io.BytesIO(data))
            elif kind == "sym":
                ti.type = tarfile.SYMTYPE
                ti.linkname = data
                tf.addfile(ti)
            elif kind == "hard":
                ti.type = tarfile.LNKTYPE
                ti.linkname = data
                tf.addfile(ti)
    return path


def test_tar_extraction_ok_and_exec_bit(tmp_path):
    t = _tar(str(tmp_path / "a.tar.gz"), [("GIS_BOX/GIS_BOX", "file", b"bin"), ("GIS_BOX/lib/x.so", "file", b"so")])
    files = um.safe_extract(t, str(tmp_path / "out"))
    assert sorted(files) == ["GIS_BOX/GIS_BOX", "GIS_BOX/lib/x.so"]


@pytest.mark.parametrize("members", [
    [("../evil", "file", b"x")], [("/abs", "file", b"x")], [("ok", "sym", "/etc/passwd")],
    [("ok", "hard", "/etc/passwd")]])
def test_tar_traversal_and_links_rejected(tmp_path, members):
    t = _tar(str(tmp_path / "e.tar.gz"), members)
    with pytest.raises(um.UpdateError) as e:
        um.safe_extract(t, str(tmp_path / "out"))
    assert e.value.code == "unsafe_archive" and not (tmp_path / "evil").exists()


def test_zip_bomb_limit(tmp_path, monkeypatch):
    z = make_zip(str(tmp_path / "b.zip"), {"big.bin": b"0" * 10_000})
    monkeypatch.setattr(um, "MAX_UNPACKED_BYTES", 1000)
    with pytest.raises(um.UpdateError):
        um.safe_extract(z, str(tmp_path / "out"))


def test_unsupported_archive(tmp_path):
    p = tmp_path / "a.rar"
    p.write_bytes(b"x")
    with pytest.raises(um.UpdateError) as e:
        um.safe_extract(str(p), str(tmp_path / "o"))
    assert e.value.code == "bad_package"


# ----------------------------------------------------------------------------- install / rollback
def _app(tmp_path):
    app = tmp_path / "app"
    (app / "lib").mkdir(parents=True)
    (app / "GIS_BOX.exe").write_bytes(b"old-exe")
    (app / "lib" / "a.dll").write_bytes(b"old-dll")
    (app / "config.txt").write_text("USER CONFIG")
    (app / "GIS_BOX_config").mkdir()
    (app / "GIS_BOX_config" / "mine.json").write_text("{}")
    (app / "data.mdb").write_bytes(b"user-db")
    return app


def _snapshot(d):
    out = {}
    for dp, _dn, fn in os.walk(d):
        for f in fn:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, d)] = open(p, "rb").read()
    return out


def _new_pkg(tmp_path, top="GIS_BOX"):
    return make_zip(str(tmp_path / "new.zip"), {
        "GIS_BOX.exe": b"new-exe", "lib/a.dll": b"new-dll", "lib/b.dll": b"brand-new",
        "config.txt": b"SHIPPED DEFAULT CONFIG", "GIS_BOX_config/mine.json": b"overwritten?",
        "data.mdb": b"x"}, top=top)


def test_install_requires_confirmation_and_verification(tmp_path):
    app, pkg = _app(tmp_path), _new_pkg(tmp_path)
    before = _snapshot(app)
    with pytest.raises(um.UpdateError) as e:
        um.install_update(pkg, str(app), str(tmp_path / "bk"), verified=True)
    assert e.value.code == "confirmation_required"
    with pytest.raises(um.UpdateError) as e:
        um.install_update(pkg, str(app), str(tmp_path / "bk"), confirmed=True, verified=False)
    assert e.value.code == "unverified" and _snapshot(app) == before


@pytest.mark.parametrize("top", ["GIS_BOX", None])
def test_install_success_preserves_user_data(tmp_path, top):
    app, pkg = _app(tmp_path), _new_pkg(tmp_path, top)
    res = um.install_update(pkg, str(app), str(tmp_path / "bk"), "2.1.0", confirmed=True, verified=True)
    s = _snapshot(app)
    assert s["GIS_BOX.exe"] == b"new-exe" and s[os.path.join("lib", "a.dll")] == b"new-dll"
    assert s[os.path.join("lib", "b.dll")] == b"brand-new"
    assert s["config.txt"] == b"USER CONFIG" and s["data.mdb"] == b"user-db"
    assert s[os.path.join("GIS_BOX_config", "mine.json")] == b"{}"
    assert {"config.txt", "data.mdb", "GIS_BOX_config/mine.json"} <= set(res.skipped)
    assert "lib/b.dll" in res.added and "GIS_BOX.exe" in res.replaced
    assert os.path.isfile(os.path.join(res.backup_dir, ".update_manifest.json"))
    assert (tmp_path / "bk" / os.path.basename(res.backup_dir) / "GIS_BOX.exe").read_bytes() == b"old-exe"
    assert not [d for d in os.listdir(tmp_path / "bk") if d.startswith(".staging")]      # staging cleaned
    assert not [f for f in s if f.endswith(".gbupd")]


def test_rollback_restores_previous_state(tmp_path):
    app, pkg = _app(tmp_path), _new_pkg(tmp_path)
    before = _snapshot(app)
    res = um.install_update(pkg, str(app), str(tmp_path / "bk"), confirmed=True, verified=True)
    assert _snapshot(app) != before
    with pytest.raises(um.UpdateError):
        um.rollback_update(res.backup_dir)
    um.rollback_update(res.backup_dir, confirmed=True)
    assert _snapshot(app) == before
    assert um.list_backups(str(tmp_path / "bk"))[0]["dir"] == res.backup_dir


def test_failed_install_rolls_back_automatically(tmp_path, monkeypatch):
    app, pkg = _app(tmp_path), _new_pkg(tmp_path)
    before = _snapshot(app)
    real = os.replace
    n = {"i": 0}

    def flaky(src, dst):
        if str(src).endswith(".gbupd"):
            n["i"] += 1
            if n["i"] == 3:
                raise PermissionError("file is locked")
        return real(src, dst)
    monkeypatch.setattr(um.os, "replace", flaky)
    with pytest.raises(um.UpdateError) as e:
        um.install_update(pkg, str(app), str(tmp_path / "bk"), confirmed=True, verified=True)
    assert e.value.code == "locked"
    assert _snapshot(app) == before                               # byte-identical to before the attempt


def test_install_refuses_git_checkout_and_bad_package(tmp_path):
    app, pkg = _app(tmp_path), _new_pkg(tmp_path)
    (app / ".git").mkdir()
    with pytest.raises(um.UpdateError) as e:
        um.install_update(pkg, str(app), str(tmp_path / "bk"), confirmed=True, verified=True)
    assert e.value.code == "git_checkout"
    (app / ".git").rmdir()
    junk = make_zip(str(tmp_path / "junk.zip"), {"readme.txt": b"hi", "other.txt": b"x"})
    before = _snapshot(app)
    with pytest.raises(um.UpdateError) as e:
        um.install_update(junk, str(app), str(tmp_path / "bk"), confirmed=True, verified=True)
    assert e.value.code == "bad_package" and _snapshot(app) == before


def test_malicious_package_changes_nothing(tmp_path):
    app = _app(tmp_path)
    evil = str(tmp_path / "evil.zip")
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("GIS_BOX.exe", b"x")
        z.writestr("../../outside.txt", b"pwn")
    before = _snapshot(app)
    with pytest.raises(um.UpdateError) as e:
        um.install_update(evil, str(app), str(tmp_path / "bk"), confirmed=True, verified=True)
    assert e.value.code == "unsafe_archive" and _snapshot(app) == before
    assert not (tmp_path / "outside.txt").exists()


def test_unverified_install_allowed_only_explicitly(tmp_path):
    app, pkg = _app(tmp_path), _new_pkg(tmp_path)
    res = um.install_update(pkg, str(app), str(tmp_path / "bk"), confirmed=True, allow_unverified=True)
    assert res.replaced


def test_prune_backups(tmp_path):
    bk = tmp_path / "bk"
    for i in range(5):
        d = bk / "2.0.0_2026010{}_000000".format(i)
        d.mkdir(parents=True)
        (d / ".update_manifest.json").write_text(json.dumps({"replaced": [], "added": [], "app_dir": "x"}))
    assert um.prune_backups(str(bk), keep=2) == 3 and len(um.list_backups(str(bk))) == 2
