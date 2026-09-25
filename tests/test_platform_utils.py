# -*- coding: utf-8 -*-
"""platform_utils + apppaths — Windows/macOS/Linux ლოგიკა (პლატფორმის მოჩვენებით)."""

import os
import sys

import pytest

import tools.apppaths as ap
import tools.platform_utils as pu


# ---- platform_utils --------------------------------------------------------
def test_open_command_is_none_on_windows_and_tool_elsewhere(monkeypatch):
    monkeypatch.setattr(pu, "IS_WINDOWS", True)
    assert pu.open_command("x") is None
    monkeypatch.setattr(pu, "IS_WINDOWS", False)
    monkeypatch.setattr(pu, "IS_MAC", True)
    assert pu.open_command("/a b/c") == ["open", "/a b/c"]
    monkeypatch.setattr(pu, "IS_MAC", False)
    assert pu.open_command("/a b/c") == ["xdg-open", "/a b/c"]


def test_open_path_uses_xdg_open_on_linux(monkeypatch):
    calls = []
    monkeypatch.setattr(pu, "IS_WINDOWS", False)
    monkeypatch.setattr(pu, "IS_MAC", False)
    monkeypatch.setattr(pu.subprocess, "Popen",
                        lambda cmd, **kw: calls.append(cmd))
    pu.open_path("/tmp/x")
    assert calls == [["xdg-open", "/tmp/x"]]


def test_fonts_are_nonempty_strings():
    for f in (pu.UI_FONT, pu.MONO_FONT, pu.GEO_FONT):
        assert isinstance(f, str) and f
    assert pu.pil_font_candidates()


def test_default_desktop_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))      # Windows expanduser
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert pu.default_desktop() == str(tmp_path)          # Desktop არ არსებობს
    (tmp_path / "Desktop").mkdir()
    assert pu.default_desktop() == str(tmp_path / "Desktop")


def test_default_desktop_reads_xdg_user_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(pu, "IS_LINUX", True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    loc = tmp_path / "Рабочий стол"
    loc.mkdir()
    (cfg / "user-dirs.dirs").write_text(
        'XDG_DESKTOP_DIR="$HOME/Рабочий стол"\n', encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    assert pu.default_desktop() == str(loc)


# ---- apppaths --------------------------------------------------------------
def test_user_config_base_per_os(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert ap.user_config_base() == os.path.join(str(tmp_path), ".config")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "x"))
    assert ap.user_config_base() == str(tmp_path / "x")
    monkeypatch.setattr(sys, "platform", "darwin")
    assert ap.user_config_base().endswith(os.path.join("Library", "Application Support"))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "L"))
    assert ap.user_config_base() == str(tmp_path / "L")


def test_data_dir_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("GIS_BOX_DATA_DIR", str(tmp_path / "custom"))
    d = ap.data_dir()
    assert d == str(tmp_path / "custom") and os.path.isdir(d)


def test_data_dir_dev_checkout_is_repo_root(monkeypatch):
    monkeypatch.delenv("GIS_BOX_DATA_DIR", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(ap, "_writable", lambda p: True)
    assert ap.data_dir() == ap._REPO_ROOT


def test_data_dir_readonly_install_uses_user_config(monkeypatch, tmp_path):
    # /opt/gis-box-ის ანალოგი: არა-frozen, მაგრამ read-only ძირი → ~/.config/GIS_BOX
    monkeypatch.delenv("GIS_BOX_DATA_DIR", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(ap, "_writable", lambda p: False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    d = ap.data_dir()
    assert d == os.path.join(str(tmp_path), "GIS_BOX") and os.path.isdir(d)


def test_data_dir_frozen_portable_beats_user_config(monkeypatch, tmp_path):
    monkeypatch.delenv("GIS_BOX_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    exe = tmp_path / "GIS_BOX"
    monkeypatch.setattr(sys, "executable", str(exe))
    (tmp_path / "GIS_BOX_config").mkdir()
    assert ap.data_dir() == str(tmp_path / "GIS_BOX_config")


def test_config_read_path_falls_back_to_bundled(monkeypatch, tmp_path):
    data, res = tmp_path / "data", tmp_path / "res"
    data.mkdir(), res.mkdir()
    (res / "map_services.txt").write_text("x", encoding="utf-8")
    monkeypatch.setenv("GIS_BOX_DATA_DIR", str(data))
    monkeypatch.setattr(ap, "resource_dir", lambda: str(res))
    assert ap.config_read_path("map_services.txt") == str(res / "map_services.txt")
    (data / "map_services.txt").write_text("mine", encoding="utf-8")   # user-ის ასლი
    assert ap.config_read_path("map_services.txt") == str(data / "map_services.txt")
