import json
import os
import threading
import zipfile

import pytest

from tools import logging_manager as lm


@pytest.fixture
def mgr(tmp_path):
    lm.clear_secrets()
    yield lm.LogManager(str(tmp_path / "logs"))
    lm.clear_secrets()


def _read(m, name):
    with open(os.path.join(m.dir, name), encoding="utf-8") as f:
        return f.read()


def test_redact_patterns():
    r = lm.redact
    assert "hunter2" not in r("password=hunter2 host=x")
    assert "hunter2" not in r("PGPASSWORD: hunter2")
    assert "abcdef123456" not in r("Authorization: Bearer abcdef123456")
    assert "pa55" not in r("postgresql://bob:pa55@db:5432/x")
    assert "bob@" not in r("postgresql://bob:pa55@db:5432/x") or ":***@" in r("postgresql://bob:pa55@db:5432/x")
    assert "ghp_" + "a" * 30 not in r("token ghp_" + "a" * 30)
    assert r("author=me passed 5 tests") == "author=me passed 5 tests"       # no false positives
    assert r(None) is None


def test_registered_secret_and_dict_keys():
    lm.register_secret("S3cr3t!x")
    try:
        assert "S3cr3t!x" not in lm.redact("connect with S3cr3t!x now")
        d = lm.redact_obj({"password": "abc", "nested": {"api_key": "k", "ok": "fine"}, "n": 5})
        assert d["password"] == "***" and d["nested"]["api_key"] == "***" and d["nested"]["ok"] == "fine" and d["n"] == 5
    finally:
        lm.clear_secrets()


def test_three_levels_route_to_files(mgr):
    mgr.user("done", "t")
    mgr.detail("crs EPSG:32637", "t")
    mgr.debug("internal", "t")
    u, d, g = _read(mgr, "user.log"), _read(mgr, "detailed.log"), _read(mgr, "debug.log")
    assert "done" in u and "crs" not in u and "internal" not in u
    assert "done" in d and "crs" in d and "internal" not in d
    assert "internal" in g and "crs" in g and "done" in g
    recs = [json.loads(x) for x in _read(mgr, "events.jsonl").splitlines()]
    assert [r["level"] for r in recs] == ["USER", "DETAIL", "DEBUG"] and recs[0]["tool"] == "t"


def test_secrets_never_reach_any_file(mgr):
    lm.register_secret("TopSecretPw")
    mgr.user("login password=TopSecretPw ok", "pg", data={"password": "TopSecretPw"})
    mgr.debug("dsn postgresql://u:TopSecretPw@h/db", "pg")
    for name in os.listdir(mgr.dir):
        if name.endswith((".log", ".jsonl")):
            assert "TopSecretPw" not in _read(mgr, name), name


def test_operation_success_recorded(mgr):
    with mgr.operation("buffer", inputs=["a.shp"], params={"dist": 5, "password": "x"}) as op:
        op.output("out.shp")
        op.detail("crs EPSG:32638")
    h = mgr.history()
    assert len(h) == 1
    r = h[0]
    assert r["tool"] == "buffer" and r["status"] == "ok" and r["inputs"] == ["a.shp"] and r["outputs"] == ["out.shp"]
    assert r["params"]["password"] == "***" and r["duration_s"] >= 0 and r["started"] and r["finished"]
    assert r["error"] is None
    assert "OK in" in _read(mgr, "user.log") and "START" in _read(mgr, "detailed.log")


def test_operation_error_recorded_and_propagates(mgr):
    with pytest.raises(ValueError):
        with mgr.operation("zone", inputs=["p.shp"]):
            raise ValueError("bad password=abc123 value")
    r = mgr.history(status="error")[0]
    assert r["status"] == "error" and "ValueError" in r["error"] and "abc123" not in r["error"]
    assert "Traceback" in _read(mgr, "debug.log") and "Traceback" not in _read(mgr, "user.log")
    assert "abc123" not in _read(mgr, "debug.log")


def test_operation_cancelled(mgr):
    with mgr.operation("dwg") as op:
        op.cancel()
    assert mgr.history()[0]["status"] == "cancelled"


def test_history_filter_and_limit(mgr):
    for t in ("a", "b", "a"):
        with mgr.operation(t):
            pass
    assert len(mgr.history(tool="a")) == 2 and len(mgr.history(limit=1)) == 1
    assert mgr.history()[0]["id"] > mgr.history()[-1]["id"]


def test_rotation(mgr, monkeypatch):
    monkeypatch.setattr(lm, "MAX_BYTES", 300)
    for i in range(40):
        mgr.user("line {} ".format(i) + "x" * 30)
    names = os.listdir(mgr.dir)
    assert "user.log.1" in names and not any(n.endswith(".log.4") for n in names)


def test_thread_safety(mgr):
    def work():
        for _ in range(20):
            with mgr.operation("t"):
                mgr.user("hi")
    ts = [threading.Thread(target=work) for _ in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(mgr.history(limit=1000)) == 100
    assert all(json.loads(x) for x in _read(mgr, "events.jsonl").splitlines())


def test_export_diagnostics_has_no_secrets(mgr, tmp_path):
    lm.register_secret("ZzSecretZz")
    mgr.user("pw ZzSecretZz")
    with mgr.operation("x", params={"token": "ZzSecretZz"}):
        pass
    out = str(tmp_path / "diag.zip")
    mgr.export_diagnostics(out)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "history.json" in names and "environment.txt" in names and any(n.startswith("logs/") for n in names)
        assert all("ZzSecretZz" not in z.read(n).decode("utf-8", "replace") for n in names)
        assert "GIS_BOX" in z.read("environment.txt").decode()
    with pytest.raises(FileExistsError):
        mgr.export_diagnostics(out)


def test_log_dir_env_and_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("GIS_BOX_LOG_DIR", str(tmp_path / "custom"))
    assert lm.log_dir() == str(tmp_path / "custom") and os.path.isdir(lm.log_dir())
    monkeypatch.delenv("GIS_BOX_LOG_DIR")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    d = lm.log_dir()
    assert "GIS_BOX" in d and (str(tmp_path / "state") in d or str(tmp_path / "local") in d)


def test_singleton(mgr):
    lm.set_manager(mgr)
    assert lm.get_manager() is mgr
    lm.set_manager(None)


def test_record_direct(mgr):
    mgr.record("pgdb_transfer", "ok", inputs=["a.mdb", "b.mdb"], outputs=["x.log"],
               params={"year": 2026}, duration=2.5)
    r = mgr.history()[0]
    assert r["tool"] == "pgdb_transfer" and r["duration_s"] == 2.5 and r["params"]["year"] == 2026


def test_pg_password_is_registered_as_secret(mgr):
    from tools import gdb2postgis_core as core
    core.PgConfig(password="Pg-Pw-9").pg_conn_string()
    try:
        assert "Pg-Pw-9" not in lm.redact("cmd ... Pg-Pw-9 ...")
    finally:
        core._set_pg_password("")
        lm.clear_secrets()
