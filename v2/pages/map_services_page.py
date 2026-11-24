"""Map services (PySide6): tile / WMS URLs to copy into ArcMap / QGIS. List comes from ``map_services.txt``."""
from __future__ import annotations

from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from tools import map_services_core as core
from v2.i18n import tr


class MapServicesPage(QWidget):
    def __init__(self, shell, path=None):
        super().__init__()
        self.shell = shell
        self.lang = shell.lang
        self.services = core.load_services(path)
        self.cards = []                              # [(name, url, widget)]
        self._build()

    def _t(self, k, **f):
        return tr(self.lang, k, **f)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        note = QLabel(self._t("ms_note"))
        note.setObjectName("muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(self._t("ms_filter"))
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)
        lay.addWidget(self.filter_edit)
        if not self.services:
            lay.addWidget(QLabel(self._t("ms_empty")))
            return
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 0, 6, 0)
        for name, url in self.services:
            card = QFrame()
            card.setFrameShape(QFrame.Shape.StyledPanel)
            cl = QVBoxLayout(card)
            title = QLabel(name)
            title.setStyleSheet("font-weight:600; background:transparent;")
            cl.addWidget(title)
            row = QHBoxLayout()
            edit = QLineEdit(url)
            edit.setReadOnly(True)                   # selectable, not editable
            row.addWidget(edit, 1)
            btn = QPushButton("📋  " + self._t("ms_copy"))
            btn.setToolTip(self._t("ms_tip"))
            btn.clicked.connect(lambda _c=False, u=url: self.copy(u))
            row.addWidget(btn)
            cl.addLayout(row)
            col.addWidget(card)
            self.cards.append((name, url, card))
        col.addStretch(1)
        area.setWidget(host)
        lay.addWidget(area, 1)

    def copy(self, url):
        QApplication.clipboard().setText(url)
        self.shell.notify(self._t("ms_copied"))

    def _apply_filter(self, text):
        q = text.strip().lower()
        for name, url, card in self.cards:
            card.setVisible(not q or q in name.lower() or q in url.lower())
