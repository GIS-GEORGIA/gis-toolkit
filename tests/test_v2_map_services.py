import os

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from tools import map_services_core as core
from v2.main_window import MainWindow
from v2.settings import Settings

SAMPLE = """Services:

Alpha Roads
https://a.example/{col}/{row}/{level}

Beta Satellite
https://b.example/vt?x={col}

Orphan line without url

https://c.example/lonely

Gamma
not-a-url-line
"""


def test_parser_pairs_names_with_urls(tmp_path):
    p = tmp_path / "ms.txt"
    p.write_text(SAMPLE, encoding="utf-8")
    got = core.load_services(str(p))
    assert got[:2] == [("Alpha Roads", "https://a.example/{col}/{row}/{level}"),
                       ("Beta Satellite", "https://b.example/vt?x={col}")]
    assert got[-len(core.EXTRA_SERVICES):] == core.EXTRA_SERVICES
    assert len(got) == 2 + len(core.EXTRA_SERVICES)          # a URL after a blank line has no name -> dropped, never guessed
    assert all(u.startswith("http") for _, u in got)


def test_missing_file_still_returns_the_builtin_services(tmp_path):
    assert core.load_services(str(tmp_path / "nope.txt")) == core.EXTRA_SERVICES


def test_matches_the_classic_tool_parser():
    """The V2 parser must not drift from the classic one on the real shipped list."""
    pytest.importorskip("tkinter")
    from tools import map_services as classic
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "map_services.txt")
    assert core.load_services(path) == classic._load_services(path)
    assert len(core.load_services(path)) > 3


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, tmp_path):
    w = MainWindow(Settings(str(tmp_path / "s.json")))
    yield w
    w.task = None
    w.close()


def _page(win):
    win.show_tool("map_services")
    return win.pages["map_services"].native


def test_page_shows_one_card_per_service_and_copies(win, qapp):
    p = _page(win)
    assert len(p.cards) == len(core.load_services()) >= 4
    name, url, _card = p.cards[0]
    p.copy(url)
    assert QApplication.clipboard().text() == url
    assert win.toast.text() in ("დაკოპირდა", "Copied") and not win.toast.isHidden()


def test_filter_hides_non_matching_cards_in_both_name_and_url(win):
    p = _page(win)
    p.show()
    p.filter_edit.setText("satellite")
    visible = [n for n, u, c in p.cards if not c.isHidden()]
    assert visible and all("satellite" in n.lower() or "satellite" in u.lower() for n, u, c in p.cards if not c.isHidden())
    assert len(visible) < len(p.cards)
    p.filter_edit.setText("zzzz-nothing")
    assert not any(not c.isHidden() for *_x, c in p.cards)
    p.filter_edit.setText("")
    assert all(not c.isHidden() for *_x, c in p.cards)
