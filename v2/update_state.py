"""Glue between the update manager and the V2 settings (no Qt)."""
from tools import update_manager as um


def record_check(settings, check):
    """Remember the outcome of a check (time, latest version/date). Returns True if an update is available."""
    u = settings["updates"]
    if check.checked_at:
        u["last_check"] = check.checked_at
    if check.latest is not None:
        u["latest_version"] = check.latest.version
        u["latest_published"] = check.latest.published
    settings.save()
    return check.status == "available"


def friendly_error(err):
    """Short text for an UpdateError code (English; the UI shows it with the original detail)."""
    texts = {
        "network": "no connection to GitHub", "rate_limit": "GitHub rate limit reached - try again later",
        "http": "GitHub returned an error", "bad_json": "unexpected answer from GitHub",
        "bad_version": "release version is not valid", "not_official": "address is not the official repository",
        "unsafe_redirect": "download was redirected to an untrusted address",
        "no_asset": "no package for this system in the release", "checksum": "checksum (SHA256) does not match",
        "size": "downloaded size does not match", "cancelled": "cancelled",
        "unsafe_archive": "the package contains unsafe paths - not installed",
        "bad_package": "the package is not a GIS_BOX application",
        "git_checkout": "this is a git checkout - use 'git pull' to update",
        "locked": "files are in use - close GIS_BOX and try again", "unverified": "package is not verified",
        "signature": "signature check failed", "signature_unsupported": "signature check needs 'cryptography'",
        "no_backup": "backup not found", "confirmation_required": "confirmation required",
    }
    code = getattr(err, "code", "")
    base = texts.get(code, str(err))
    detail = getattr(err, "detail", "")
    return "{} ({})".format(base, detail) if detail and code not in ("cancelled",) else base


def installable_target():
    return um.default_app_dir()
