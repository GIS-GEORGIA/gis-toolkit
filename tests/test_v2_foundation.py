import os
import subprocess
from unittest import mock

from tools import env_check, version
from tools import gdb2postgis_core as core


def test_version_semver():
    assert version.parse("v2.0.0") == ((2, 0, 0), False)
    assert version.parse("2.1.0-rc.1")[1] is True
    assert version.is_newer("2.0.1", "2.0.0")
    assert version.is_newer("2.0.0", "2.0.0-dev")
    assert not version.is_newer("1.9.9", "2.0.0")


def test_env_check_runs_and_reports():
    items = env_check.collect()
    assert any(i["name"] == "python" for i in items)
    assert "GIS_BOX environment" in env_check.report(items)


def test_pg_password_not_in_argv_but_in_env():
    pg = core.PgConfig(password="S3cret!")
    cs = pg.pg_conn_string()
    assert "S3cret" not in cs and "password" not in cs
    assert core._child_env(None).get("PGPASSWORD") == "S3cret!"
    core._set_pg_password("")


def test_pg_password_never_logged_in_command():
    pg = core.PgConfig(password="S3cret!")
    cmd = ["ogr2ogr", "-f", "PostgreSQL", pg.pg_conn_string(), "x"]
    assert "S3cret" not in " ".join(cmd)
    core._set_pg_password("")
