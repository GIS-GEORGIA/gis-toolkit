import hashlib
import io
import json
import os
import time
import urllib.error
import zipfile

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from tools import update_manager as um
from tools import version
from v2.main_window import MainWindow
from v2.settings import Settings

REPO = version.REPO
DL = "https://github.com/{}/releases/download/v9.0.0".format(REPO)


class Resp:
    def __init__(self, data):
        self._b = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))}

    def read(self, n=-1):
        return self._b.read(n)

    def close(self):
        pass


class Net:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, headers=None):
        self.calls.append(url)
        v = self.routes.get(url)
        if v is None:
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        if isinstance(v, Exception):
            raise v
        return Resp(v)


def _pkg_bytes():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("GIS_BOX/GIS_BOX.exe", b"NEW")
        z.writestr("GIS_BOX/lib/new.dll", b"N")
        z.writestr("GIS_BOX/config.txt", b"shipped")
    return b.getvalue()


def _routes(digest=True, tag="v9.0.0"):
    data = _pkg_bytes()
    asset = {"name": "GIS_BOX-windows-x64.zip", "size": len(data),
             "browser_download_url": DL + "/GIS_BOX-windows-x64.zip"}
    if digest:
        asset["digest"] = "sha256:" + hashlib.sha256(data).hexdigest()
    rel = {"tag_name": tag, "name": tag, "body": "Big release notes", "published_at": "2026-06-01T00:00:00Z",
           "prerelease": False, "assets": [asset]}
    return {um.LATEST_URL: json.dumps(rel).encode(), DL + "/GIS_BOX-windows-x64.zip": data}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, tmp_path):
    w = MainWindow(Settings(str(tmp_path / "s.json")))
    yield w
    w.task = None
    w.close()


def wait_for(cond, timeout=15):
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return cond()


def settle():
    time.sleep(0.2)
    QCoreApplication.processEvents()


def _page(win, net):
    win.show_tool("updates")
    p = win.pages["updates"].native
    p.opener = net
    return p


@pytest.fixture(autouse=True)
def pick_first_asset(monkeypatch):
    """Tests run on any OS: always pick the zip asset."""
    monkeypatch.setattr(um, "select_asset", lambda rel, *a, **k: rel.assets[0])


def test_updates_tool_registered_and_options_persist(win):
    p = _page(win, Net({}))
    assert p.v_current.text() == version.__version__
    p.cb_auto.setChecked(True)
    p.cb_pre.setChecked(True)
    p.cb_notify.setChecked(False)
    s = Settings(win.settings.path)
    assert s["updates"]["auto_check"] and s["updates"]["prerelease"] and not s["updates"]["notify"]


def test_check_now_available_shows_notes_and_enables_download(win):
    p = _page(win, Net(_routes()))
    assert not p.btn_dl.isEnabled()
    p.check_now()
    assert wait_for(lambda: win.task is None and p.check is not None)
    assert p.check.status == "available"
    assert "9.0.0" in p.status.text() and "Big release notes" in p.notes.toPlainText()
    assert p.v_latest.text() == "9.0.0" and p.v_date.text() == "2026-06-01"
    assert p.btn_dl.isEnabled() and not p.btn_inst.isEnabled()
    assert win.settings["updates"]["latest_version"] == "9.0.0" and win.settings["updates"]["last_check"]


def test_check_error_is_shown_not_raised(win):
    p = _page(win, Net({um.LATEST_URL: urllib.error.URLError("offline")}))
    p.check_now()
    assert wait_for(lambda: win.task is None and p.check is not None)
    assert p.check.status == "error" and "GitHub" in p.status.text()
    assert not p.btn_dl.isEnabled()


def test_download_needs_consent_then_installs_with_backup_and_rollback(win, tmp_path, monkeypatch):
    app = tmp_path / "app"
    (app / "lib").mkdir(parents=True)
    (app / "GIS_BOX.exe").write_bytes(b"OLD")
    (app / "config.txt").write_text("MINE")
    monkeypatch.setattr(um, "default_app_dir", lambda: str(app))
    net = Net(_routes())
    p = _page(win, net)
    p.check_now()
    assert wait_for(lambda: win.task is None and p.check is not None)

    # 1) declined download -> the package URL is never requested
    monkeypatch.setattr(p, "_confirm", lambda t: False)
    p.download()
    settle()
    assert not any(c.endswith(".zip") for c in net.calls) and p.dl is None

    # 2) confirmed download -> verified through the API digest
    asked = []
    monkeypatch.setattr(p, "_confirm", lambda t: asked.append(t) or True)
    p.download()
    assert wait_for(lambda: win.task is None and p.dl is not None)
    assert p.dl.verified and "github.com" in asked[0] and p.btn_inst.isEnabled()
    assert (app / "GIS_BOX.exe").read_bytes() == b"OLD"                       # nothing installed yet

    # 3) declined install -> untouched
    monkeypatch.setattr(p, "_confirm", lambda t: False)
    p.install()
    settle()
    assert (app / "GIS_BOX.exe").read_bytes() == b"OLD"

    # 4) confirmed install -> replaced, user config kept, backup exists
    monkeypatch.setattr(p, "_confirm", lambda t: True)
    p.install()
    assert wait_for(lambda: win.task is None and p.dl is None)
    assert (app / "GIS_BOX.exe").read_bytes() == b"NEW" and (app / "lib" / "new.dll").exists()
    assert (app / "config.txt").read_text() == "MINE"
    assert um.list_backups(os.path.join(os.environ["GIS_BOX_V2_DIR"], "update_backups"))

    # 5) rollback
    p.rollback()
    assert wait_for(lambda: win.task is None and (app / "GIS_BOX.exe").read_bytes() == b"OLD")
    assert not (app / "lib" / "new.dll").exists()


def test_unverified_package_needs_second_confirmation(win, tmp_path, monkeypatch):
    app = tmp_path / "app"
    app.mkdir()
    (app / "GIS_BOX.exe").write_bytes(b"OLD")
    monkeypatch.setattr(um, "default_app_dir", lambda: str(app))
    p = _page(win, Net(_routes(digest=False)))
    p.check_now()
    assert wait_for(lambda: win.task is None and p.check is not None)
    monkeypatch.setattr(p, "_confirm", lambda t: True)
    p.download()
    assert wait_for(lambda: win.task is None and p.dl is not None)
    assert not p.dl.verified
    answers = []

    def confirm(t):
        answers.append(t)
        return len(answers) == 1                      # yes to install, NO to "install unverified"
    monkeypatch.setattr(p, "_confirm", confirm)
    p.install()
    settle()
    assert len(answers) == 2 and (app / "GIS_BOX.exe").read_bytes() == b"OLD"


def test_install_failure_is_reported_and_app_untouched(win, tmp_path, monkeypatch):
    app = tmp_path / "app"
    app.mkdir()
    (app / ".git").mkdir()                            # a developer checkout must never be overwritten
    (app / "GIS_BOX.exe").write_bytes(b"OLD")
    monkeypatch.setattr(um, "default_app_dir", lambda: str(app))
    p = _page(win, Net(_routes()))
    p.check_now()
    assert wait_for(lambda: win.task is None and p.check is not None)
    monkeypatch.setattr(p, "_confirm", lambda t: True)
    p.download()
    assert wait_for(lambda: win.task is None and p.dl is not None)
    p.install()
    assert wait_for(lambda: win.task is None and win.toast.property("kind") == "error")
    assert "git" in win.toast.text().lower() and (app / "GIS_BOX.exe").read_bytes() == b"OLD"


def test_auto_check_disabled_by_default_makes_no_network_call(win):
    net = Net(_routes())
    win.update_opener = net
    win.auto_update_check()
    settle()
    assert net.calls == [] and win.task is None


def test_auto_check_when_enabled_notifies_once_a_day(win):
    net = Net(_routes())
    win.update_opener = net
    win.settings["updates"].update(auto_check=True, notify=True, last_check="")
    win.auto_update_check()
    assert wait_for(lambda: win.task is None and net.calls)
    assert wait_for(lambda: "9.0.0" in win.toast.text())
    assert win.settings["updates"]["last_check"]
    n = len(net.calls)
    win.auto_update_check()                           # just checked -> not due again
    settle()
    assert len(net.calls) == n


def test_auto_check_respects_notify_off(win):
    win.update_opener = Net(_routes())
    win.settings["updates"].update(auto_check=True, notify=False, last_check="")
    win.toast.setText("")
    win.auto_update_check()
    assert wait_for(lambda: win.task is None and win.settings["updates"]["latest_version"] == "9.0.0")
    assert win.toast.text() == ""
