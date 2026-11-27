import os

import pytest

from tools import pgdb_transfer_core as c


def test_final_path_is_next_to_destination_and_stamped(tmp_path):
    dst = tmp_path / "my dst.mdb"
    p = c.final_output_path(str(dst), stamp="20260101_120000")
    assert os.path.dirname(p) == str(tmp_path)
    assert os.path.basename(p) == "my_dst_FINAL_20260101_120000.mdb"


def test_final_copy_is_a_new_file_and_destination_is_untouched(tmp_path):
    dst = tmp_path / "dst.mdb"
    dst.write_bytes(b"x" * 5000)
    before = (dst.read_bytes(), dst.stat().st_mtime_ns)
    out = c.final_output_path(str(dst), stamp="s")
    assert c.make_final_copy(str(dst), out) == out
    assert open(out, "rb").read() == before[0]
    assert (dst.read_bytes(), dst.stat().st_mtime_ns) == before
    assert not os.path.exists(out + ".part")


def test_final_copy_never_overwrites(tmp_path):
    dst = tmp_path / "dst.mdb"
    dst.write_bytes(b"a")
    out = tmp_path / "out.mdb"
    out.write_bytes(b"keep")
    with pytest.raises(c.TransferError) as e:
        c.make_final_copy(str(dst), str(out))
    assert e.value.code == "exists" and out.read_bytes() == b"keep"


def test_final_copy_missing_destination(tmp_path):
    with pytest.raises(c.TransferError) as e:
        c.make_final_copy(str(tmp_path / "nope.mdb"), str(tmp_path / "o.mdb"))
    assert e.value.code == "missing"


def test_size_warning_only_near_the_2gb_limit(tmp_path, monkeypatch):
    f = tmp_path / "a.mdb"
    f.write_bytes(b"x")
    assert c.size_warning(str(f)) is None                      # 700 MB-class files are fine
    monkeypatch.setattr(os.path, "getsize", lambda p: int(1.6 * 1024 ** 3))
    mb, pct = c.size_warning(str(f))
    assert 1500 < mb < 1700 and 75 < pct < 85
    monkeypatch.setattr(os.path, "getsize", lambda p: 700 * 1024 ** 2)
    assert c.size_warning(str(f)) is None
