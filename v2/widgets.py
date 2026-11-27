"""Small reusable V2 widgets: a wrapping flow layout, category badge icons and the tool card."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy, QVBoxLayout

_ICON_CACHE: dict = {}


class FlowLayout(QLayout):
    """Lays items out left to right and wraps to the next row when the width runs out (responsive grid)."""

    def __init__(self, parent=None, spacing=12):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):                                   # noqa: N802 - Qt API
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):                                       # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):                                       # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):                             # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self):                               # noqa: N802
        return True

    def heightForWidth(self, width):                           # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), dry=True)

    def setGeometry(self, rect):                               # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, dry=False)

    def sizeHint(self):                                        # noqa: N802
        return self.minimumSize()

    def minimumSize(self):                                     # noqa: N802
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, dry):
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, row_h = r.x(), r.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            if x + hint.width() > r.right() + 1 and row_h > 0:   # wrap
                x, y, row_h = r.x(), y + row_h + self._spacing, 0
            if not dry:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            row_h = max(row_h, hint.height())
        return y + row_h - rect.y() + m.bottom()


def badge_icon(text, color, size=28, fg="#ffffff"):
    """A rounded square in ``color`` with a short code (e.g. "CRS") - the same on every platform, no image files.
    Drawn at 2x and 3x as well so it stays sharp at 150-300 % display scaling."""
    key = (text, color, size, fg)
    icon = _ICON_CACHE.get(key)
    if icon is not None:
        return icon
    icon = QIcon()
    for scale in (1, 2, 3):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRect(0, 0, size * scale, size * scale), 7 * scale, 7 * scale)
        f = QFont()
        f.setBold(True)
        f.setPixelSize(max(7, int(size * scale * (0.42 if len(text) <= 2 else 0.34))))
        p.setFont(f)
        p.setPen(QColor(fg))
        p.drawText(QRect(0, 0, size * scale, size * scale), Qt.AlignmentFlag.AlignCenter, text)
        p.end()
        pm.setDevicePixelRatio(scale)
        icon.addPixmap(pm)
    _ICON_CACHE[key] = icon
    return icon


class ToolCard(QPushButton):
    """A clickable card for one tool: badge, name, short description, favorite star.

    It is a QPushButton underneath, so hover / pressed / focus states and keyboard activation (Space) work
    out of the box; the labels inside ignore the mouse so the whole card reacts."""

    WIDTH = 248

    def __init__(self, tool, lang, icon, favorite=False, parent=None):
        super().__init__(parent)
        self.tool_id = tool.id
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(self.WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip(tool.desc[lang])
        self.setAccessibleName(tool.name[lang])
        self.setAccessibleDescription(tool.desc[lang])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(10)
        badge = QLabel()
        badge.setPixmap(icon.pixmap(QSize(28, 28)))
        badge.setFixedSize(28, 28)
        head.addWidget(badge)
        name = QLabel(tool.name[lang])
        name.setObjectName("cardTitle")
        name.setWordWrap(True)
        head.addWidget(name, 1)
        if favorite:
            star = QLabel("★")
            star.setObjectName("accent")
            star.setToolTip("")
            head.addWidget(star, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)
        desc = QLabel(tool.desc[lang])
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        lay.addWidget(desc)
        lay.addStretch(1)
        for lb in self.findChildren(QLabel):
            lb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedHeight(max(112, lay.sizeHint().height()))

    def sizeHint(self):                                        # noqa: N802
        return QSize(self.WIDTH, self.height())
