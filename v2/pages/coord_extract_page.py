"""Map coordinate extractor (PySide6): OCR a printed No/X/Y table, or geo-reference a map by grid points.

The map comes from an image file, a PDF page (PyMuPDF), the clipboard (e.g. a Win+Shift+S snip) or a screen grab
of any window. Two tabs, as in the classic tool:

* OCR table     - drag a box around the coordinate table, read it in the background (rapidocr / tesseract /
                  easyocr), fix mistakes in the editable table, export Excel / CSV / JSON.
* Geo-reference - click grid intersections and type their real X/Y (affine fit, RMSE shown), click polygon
                  corners, compute their real coordinates and the area.

Logic (OCR, affine fit, export) lives in ``tools/coordextract`` and is shared with the classic tool; texts are the
classic ``coordextract.i18n`` catalogue plus a few V2 extras. Nothing is written without a file the user picked;
"Format Excel" changes the chosen workbook only after a confirmation.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

EXTRA = {
    "btn_paste": {"ka": "ჩასმა ბუფერიდან", "en": "Paste image"},
    "tip_paste": {"ka": "ბუფერში არსებული სურათის ჩასმა (მაგ. Win+Shift+S-ით ამოჭრილი).",
                  "en": "Paste the image on the clipboard (e.g. a Win+Shift+S snip)."},
    "no_clip": {"ka": "ბუფერში სურათი არ არის.", "en": "There is no image on the clipboard."},
    "img_pasted": {"ka": "ჩასმულია ბუფერიდან", "en": "Pasted from the clipboard"},
    "tip_grab": {"ka": "GIS_BOX დროებით დაიმალება — მონიშნე ეკრანის ნებისმიერი არე (PDF, ბრაუზერი…). Esc — გაუქმება.",
                 "en": "GIS_BOX hides for a moment - drag over any part of the screen (PDF, browser…). Esc cancels."},
    "tip_wheel": {"ka": "ბორბალი — მიახლოება/დაშორება; გადათრევა — გადაადგილება (როცა რეჟიმი არ არის არჩეული).",
                  "en": "Wheel zooms; drag pans (when no mode is active)."},
    "format_confirm": {"ka": "„{name}“-ში დაემატება გასუფთავებული ასლი (№/X/Y), E6 უჯრიდან. ფაილი შეიცვლება, "
                             "მისი არსებული ცხრილი — არა. გავაგრძელო?",
                       "en": "A cleaned copy (№/X/Y) will be added to \"{name}\" starting at cell E6. The file is "
                             "changed, its existing table is not. Continue?"},
    "export_lbl": {"ka": "ექსპორტი:", "en": "Export:"},
    "tip_format": {"ka": "არსებულ Excel-ს (№/X/Y) გვერდით დაემატება გასუფთავებული, ჩარჩოებიანი ასლი E6-დან.",
                   "en": "Adds a cleaned, bordered copy (№/X/Y) next to the table of an existing Excel file, at E6."},
}

ROW_COLS = ("no", "x", "y")
CP_COLS = ("px", "py", "X", "Y")


def _fmt(v):
    if v is None or v == "":
        return ""
    v = round(float(v), 3)                 # 500020.0000001 from the affine fit -> "500020"
    return str(int(v)) if v.is_integer() else f"{v:.3f}"


def bgr_to_qimage(img):
    """BGR/gray numpy image -> independent QImage (RGB888)."""
    import cv2
    import numpy as np
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    rgb = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def qimage_to_bgr(qimg):
    """QImage (any format) -> BGR numpy image."""
    import numpy as np
    q = qimg.convertToFormat(QImage.Format.Format_RGB888)
    w, h, bpl = q.width(), q.height(), q.bytesPerLine()
    arr = np.frombuffer(q.constBits(), dtype=np.uint8, count=bpl * h).reshape(h, bpl)[:, : 3 * w]
    return np.ascontiguousarray(arr.reshape(h, w, 3)[:, :, ::-1])


# ---------------------------------------------------------------------------------------------- canvas
class MapView(QGraphicsView):
    """Image view whose mouse signals report IMAGE pixel coordinates."""

    pressed = Signal(float, float)
    moved = Signal(float, float)
    released = Signal(float, float)
    zoomed = Signal()                       # marks are redrawn so they keep their on-screen size
    ZOOM_STEP = 1.25

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QColor("#2b2b2b"))
        self.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.pix_item = None
        self.capture_mouse = False          # True while a mode (crop/control/polygon) is active
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def set_image(self, qimg):
        self.scene().clear()
        self.pix_item = QGraphicsPixmapItem(QPixmap.fromImage(qimg))
        self.pix_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene().addItem(self.pix_item)
        self.scene().setSceneRect(QRectF(0, 0, qimg.width(), qimg.height()))
        self.fit()

    def fit(self):
        if self.pix_item is not None:
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self.zoomed.emit()

    def zoom(self, factor):
        if self.pix_item is None:
            return
        cur = self.transform().m11()
        factor = max(0.05 / cur, min(8.0 / cur, factor))
        self.scale(factor, factor)
        self.zoomed.emit()

    def set_capture(self, on):
        self.capture_mouse = on
        self.setDragMode(QGraphicsView.DragMode.NoDrag if on else QGraphicsView.DragMode.ScrollHandDrag)
        self.viewport().setCursor(Qt.CursorShape.CrossCursor if on else Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, e):
        self.zoom(self.ZOOM_STEP if e.angleDelta().y() > 0 else 1 / self.ZOOM_STEP)

    def _img(self, e):
        p = self.mapToScene(e.position().toPoint())
        return p.x(), p.y()

    def mousePressEvent(self, e):
        if self.capture_mouse and self.pix_item is not None and e.button() == Qt.MouseButton.LeftButton:
            self.pressed.emit(*self._img(e))
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.capture_mouse and self.pix_item is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.moved.emit(*self._img(e))
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self.capture_mouse and self.pix_item is not None and e.button() == Qt.MouseButton.LeftButton:
            self.released.emit(*self._img(e))
            return
        super().mouseReleaseEvent(e)


# ---------------------------------------------------------------------------------------------- screen grab
class ScreenSnip(QWidget):
    """Frozen full-desktop screenshot; the user drags a rectangle, Esc cancels. Calls ``done(bgr or None)``."""

    def __init__(self, shot_bgr, hint, done):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.shot = shot_bgr
        self.done = done
        self.hint = hint
        self.start = self.end = None
        self.pix = QPixmap.fromImage(bgr_to_qimage(shot_bgr))
        geo = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(geo)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._finished = False

    def paintEvent(self, _e):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.pix)
        p.fillRect(self.rect(), QColor(0, 0, 0, 90))
        if self.start and self.end:
            r = QRectF(self.start, self.end).normalized()
            src = self._to_img(r)
            p.drawPixmap(r, self.pix, src)
            p.setPen(QPen(QColor("#00e0ff"), 2))
            p.drawRect(r)
        p.setPen(QColor("white"))
        f = p.font()
        f.setPointSize(14)
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect().adjusted(0, 20, 0, 0), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   self.hint)

    def _to_img(self, r):
        sx = self.pix.width() / max(1, self.width())
        sy = self.pix.height() / max(1, self.height())
        return QRectF(r.x() * sx, r.y() * sy, r.width() * sx, r.height() * sy)

    def mousePressEvent(self, e):
        self.start = self.end = e.position()
        self.update()

    def mouseMoveEvent(self, e):
        if self.start is not None:
            self.end = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        if self.start is None:
            return self._finish(None)
        r = self._to_img(QRectF(self.start, e.position()).normalized()).toRect()
        if r.width() < 8 or r.height() < 8:
            return self._finish(None)
        h, w = self.shot.shape[:2]
        x0, y0 = max(0, r.x()), max(0, r.y())
        x1, y1 = min(w, r.x() + r.width()), min(h, r.y() + r.height())
        self._finish(self.shot[y0:y1, x0:x1].copy())

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._finish(None)

    def _finish(self, img):
        if self._finished:
            return
        self._finished = True
        self.close()
        self.done(img)


def grab_desktop():
    """Whole virtual desktop (all monitors) as a BGR image."""
    import cv2
    import numpy as np
    from PIL import ImageGrab
    img = ImageGrab.grab(all_screens=True)
    return cv2.cvtColor(np.array(img)[:, :, :3], cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------------------------------------- dialogs
class XYDialog(QDialog):
    def __init__(self, parent, px, py, z):
        super().__init__(parent)
        self.setWindowTitle(z("cp_title"))
        lay = QFormLayout(self)
        lay.addRow(QLabel(z("cp_pixel", px=px, py=py)))
        self.x_edit, self.y_edit = QLineEdit(), QLineEdit()
        lay.addRow(z("cp_realx"), self.x_edit)
        lay.addRow(z("cp_realy"), self.y_edit)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)
        self.z = z
        self.result_xy = None

    def _ok(self):
        xy = parse_xy(self.x_edit.text(), self.y_edit.text())
        if xy is None:
            QMessageBox.warning(self, self.z("cp_invalid_title"), self.z("cp_invalid"))
            return
        self.result_xy = xy
        self.accept()


def parse_xy(x, y):
    try:
        return float(str(x).strip().replace(",", ".")), float(str(y).strip().replace(",", "."))
    except ValueError:
        return None


# ---------------------------------------------------------------------------------------------- page
class CoordExtractPage(QWidget):
    TOOL = "coord_extractor"

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.lang = shell.lang
        from tools.coordextract.i18n import TR
        self.cat = TR
        self.cv_img = None
        self.mode = None
        self.crop_rect = None                  # (x0, y0, x1, y1) in image pixels
        self.crop_start = None
        self.control_points = []
        self.polygon_px = []
        self.model = None
        self.pdf_doc = None
        self.pdf_path = ""
        self.pdf_page = 0
        self.pdf_dpi = 200
        self._overlay = []
        self._last_xlsx = ""
        self._backends_loaded = False
        st = shell.settings["tool_state"].get(self.TOOL, {})
        self._last_dir = st.get("last_dir", "")
        self._want_backend = st.get("backend", "")
        self._build()
        shell.busy_changed.connect(self._set_busy)

    def _z(self, key, **f):
        d = self.cat.get(key) or EXTRA.get(key) or {}
        s = d.get(self.lang) or d.get("en") or key
        return s.format(**f) if f else s

    # ------------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        self.img_btn = self._btn(self._z("btn_open_image"), self.open_image)
        self.pdf_btn = self._btn(self._z("btn_open_pdf"), self.open_pdf)
        self.paste_btn = self._btn(self._z("btn_paste"), self.paste_image, self._z("tip_paste"))
        self.grab_btn = self._btn(self._z("btn_grab"), self.grab_screen, self._z("tip_grab"))
        for b in (self.img_btn, self.pdf_btn, self.paste_btn, self.grab_btn):
            bar.addWidget(b)
        self.prev_btn = self._btn("◀", self.prev_page)
        self.page_lbl = QLabel(self._z("page_dash"))
        self.next_btn = self._btn("▶", self.next_page)
        for b in (self.prev_btn, self.next_btn):
            b.setFixedWidth(34)
        bar.addSpacing(8)
        bar.addWidget(self.prev_btn)
        bar.addWidget(self.page_lbl)
        bar.addWidget(self.next_btn)
        bar.addSpacing(8)
        self.view = MapView()
        self.view.setToolTip(self._z("tip_wheel"))
        bar.addWidget(self._btn(self._z("btn_zoom_in"), lambda: self.view.zoom(MapView.ZOOM_STEP)))
        bar.addWidget(self._btn(self._z("btn_zoom_out"), lambda: self.view.zoom(1 / MapView.ZOOM_STEP)))
        bar.addWidget(self._btn(self._z("btn_fit"), self.view.fit))
        bar.addStretch(1)
        lay.addLayout(bar)
        self._set_page_controls(False)

        self.status = QLabel(self._z("status_start"))
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.view)
        self.view.pressed.connect(self._on_press)
        self.view.moved.connect(self._on_move)
        self.view.released.connect(self._on_release)
        self.view.zoomed.connect(self._redraw)
        self.view.setMinimumWidth(240)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_ocr_tab(), self._z("tab_ocr"))
        self.tabs.addTab(self._build_geo_tab(), self._z("tab_geo"))
        self.tabs.setMinimumWidth(380)
        split.addWidget(self.tabs)
        split.setCollapsible(0, False)
        split.setCollapsible(1, False)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.split = split
        lay.addWidget(split, 1)

    def _btn(self, text, slot, tip=None):
        b = QPushButton(text)
        b.clicked.connect(lambda _c=False: slot())
        if tip:
            b.setToolTip(tip)
        return b

    def _table(self, cols, editable=True):
        t = QTableWidget(0, len(cols))
        t.setHorizontalHeaderLabels([c.upper() if c in ROW_COLS else c for c in cols])
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        if not editable:
            t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        return t

    def _export_row(self, table_getter):
        row = QHBoxLayout()
        row.addWidget(QLabel(self._z("export_lbl")))
        for fmt, label, key in (("xlsx", "Excel", "exp_excel"), ("csv", "CSV", "exp_csv"), ("json", "JSON", "exp_json")):
            row.addWidget(self._btn(label, lambda f=fmt: self.export(table_getter(), f), self._z(key)))
        row.addStretch(1)
        box = QVBoxLayout()
        box.addLayout(row)
        fr = QHBoxLayout()
        fr.addWidget(self._btn(self._z("exp_format"), self.format_excel, self._z("tip_format")))
        fr.addStretch(1)
        box.addLayout(fr)
        return box

    def _build_ocr_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        r = QHBoxLayout()
        r.addWidget(QLabel(self._z("lbl_backend")))
        self.backend_combo = QComboBox()
        self.backend_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.backend_combo.setMinimumWidth(140)
        r.addWidget(self.backend_combo)
        r.addStretch(1)
        lay.addLayout(r)
        self.mark_btn = self._btn(self._z("ocr_mark"), lambda: self.set_mode("crop"))
        self.ocr_btn = self._btn(self._z("ocr_read"), self.run_ocr)
        self.ocr_btn.setObjectName("primary")
        lay.addWidget(self.mark_btn)
        lay.addWidget(self.ocr_btn)
        self.ocr_table = self._table(ROW_COLS)
        lay.addWidget(self.ocr_table, 1)
        er = QHBoxLayout()
        er.addWidget(self._btn(self._z("tbl_add_row"), self.add_row))
        er.addWidget(self._btn(self._z("tbl_del_row"), lambda: self._delete_rows(self.ocr_table)))
        er.addStretch(1)
        lay.addLayout(er)
        lay.addLayout(self._export_row(lambda: self.ocr_table))
        tip = QLabel(self._z("ocr_tip"))
        tip.setObjectName("muted")
        lay.addWidget(tip)
        return w

    def _build_geo_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self._bold(self._z("geo_cp_header")))
        lay.addWidget(self._btn(self._z("geo_add_cp"), lambda: self.set_mode("control")))
        self.cp_table = self._table(CP_COLS, editable=False)
        self.cp_table.setMaximumHeight(150)
        lay.addWidget(self.cp_table)
        lay.addWidget(self._btn(self._z("geo_del_cp"), self.delete_control_points))
        self.fit_lbl = QLabel(self._z("fit_none"))
        lay.addWidget(self.fit_lbl)
        lay.addSpacing(6)
        lay.addWidget(self._bold(self._z("geo_poly_header")))
        lay.addWidget(self._btn(self._z("geo_add_vertex"), lambda: self.set_mode("polygon")))
        clr = self._btn(self._z("geo_clear_poly"), self.clear_polygon)
        pr = QHBoxLayout()
        pr.addWidget(clr)
        pr.addStretch(1)
        lay.addLayout(pr)
        cb = self._btn(self._z("geo_compute"), self.compute_geo)
        cb.setObjectName("primary")
        lay.addWidget(cb)
        self.geo_table = self._table(ROW_COLS)
        lay.addWidget(self.geo_table, 1)
        self.area_lbl = QLabel(self._z("area_none"))
        lay.addWidget(self.area_lbl)
        lay.addLayout(self._export_row(lambda: self.geo_table))
        return w

    @staticmethod
    def _bold(text):
        lb = QLabel(text)
        lb.setStyleSheet("font-weight:600; background:transparent;")
        return lb

    def showEvent(self, event):
        super().showEvent(event)
        if not self._backends_loaded:                 # importing an OCR engine takes a moment: only on first display
            self._backends_loaded = True
            total = max(1, self.split.width())
            self.split.setSizes([int(total * 0.6), total - int(total * 0.6)])   # the map gets the larger part
            self.load_backends()

    def load_backends(self):
        from tools.coordextract.ocr import available_backends
        backs = available_backends()
        self.backend_combo.clear()
        self.backend_combo.addItems(backs or [self._z("backend_none")])
        if self._want_backend in backs:
            self.backend_combo.setCurrentText(self._want_backend)
        self._backends = backs

    def _set_busy(self, busy):
        for b in (self.ocr_btn, self.img_btn, self.pdf_btn, self.paste_btn, self.grab_btn):
            b.setEnabled(not busy)
        if not busy:
            self._set_page_controls(self.pdf_doc is not None and self.pdf_doc.page_count > 1)
        else:
            self._set_page_controls(False)

    # ------------------------------------------------------------------ dialogs (patched in tests)
    def _info(self, title, text):
        QMessageBox.information(self, title, text)

    def _error(self, title, text):
        QMessageBox.critical(self, title, text)

    def _confirm(self, text):
        return QMessageBox.question(self, "GIS_BOX", text) == QMessageBox.StandardButton.Yes

    def _open_name(self, title, filt, start=""):
        return QFileDialog.getOpenFileName(self, title, start or self._last_dir, filt)[0]

    def _save_name(self, filt, ext):
        p = QFileDialog.getSaveFileName(self, self._z("exp_" + ("excel" if ext == ".xlsx" else ext[1:])),
                                        self._last_dir, filt)[0]
        if p and not os.path.splitext(p)[1]:
            p += ext
        return p

    def _ask_xy(self, px, py):
        dlg = XYDialog(self, px, py, self._z)
        return dlg.result_xy if dlg.exec() else None

    def _remember(self, **kw):
        st = self.shell.settings["tool_state"].setdefault(self.TOOL, {})
        st.update(kw)
        self.shell.settings.save()

    # ------------------------------------------------------------------ image sources
    def set_image(self, img, source):
        """Load a BGR image and reset every per-image state."""
        self.cv_img = img
        self.control_points.clear()
        self.polygon_px.clear()
        self.crop_rect = None
        self.model = None
        for t in (self.cp_table, self.geo_table, self.ocr_table):
            t.setRowCount(0)
        self.fit_lbl.setText(self._z("fit_none"))
        self.area_lbl.setText(self._z("area_none"))
        self._overlay = []
        self.view.set_image(bgr_to_qimage(img))
        self.set_mode(None)
        self.status.setText(self._z("img_size", src=source, w=img.shape[1], h=img.shape[0]))
        QTimer.singleShot(0, self.view.fit)

    def load_image_file(self, path):
        import cv2
        import numpy as np
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)   # works with non-ASCII paths
        if img is None:
            self._error(self._z("err_title"), self._z("img_read_err", path=path))
            return False
        self._close_pdf()
        self.set_image(img, self._z("img_loaded", name=os.path.basename(path)))
        self._last_dir = os.path.dirname(path)
        self._remember(last_dir=self._last_dir)
        return True

    def open_image(self):
        p = self._open_name(self._z("open_map_title"),
                            "{} (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp);;{} (*.*)".format(
                                self._z("ft_images"), self._z("ft_all")))
        if p:
            self.load_image_file(os.path.normpath(p))

    def open_pdf(self, path=None):
        path = path or self._open_name(self._z("open_pdf_title"), "PDF (*.pdf);;{} (*.*)".format(self._z("ft_all")))
        if not path:
            return False
        from tools.coordextract import capture
        try:
            doc = capture.open_pdf(path)
        except Exception as e:                              # noqa: BLE001
            self._error(self._z("pdf_cannot_title"), f"{type(e).__name__}: {e}")
            return False
        self._close_pdf()
        self.pdf_doc, self.pdf_path, self.pdf_page = doc, path, 0
        self._render_pdf_page()
        self._set_page_controls(doc.page_count > 1)
        self._last_dir = os.path.dirname(path)
        self._remember(last_dir=self._last_dir)
        return True

    def _render_pdf_page(self):
        from tools.coordextract import capture
        img = capture.render_page(self.pdf_doc, self.pdf_page, dpi=self.pdf_dpi)
        self.set_image(img, self._z("pdf_page", name=os.path.basename(self.pdf_path), page=self.pdf_page + 1,
                                    total=self.pdf_doc.page_count))
        self.page_lbl.setText(f"{self.pdf_page + 1} / {self.pdf_doc.page_count}")

    def prev_page(self):
        if self.pdf_doc is not None and self.pdf_page > 0:
            self.pdf_page -= 1
            self._render_pdf_page()

    def next_page(self):
        if self.pdf_doc is not None and self.pdf_page < self.pdf_doc.page_count - 1:
            self.pdf_page += 1
            self._render_pdf_page()

    def _set_page_controls(self, enabled):
        self.prev_btn.setEnabled(enabled)
        self.next_btn.setEnabled(enabled)

    def _close_pdf(self):
        if self.pdf_doc is not None:
            try:
                self.pdf_doc.close()
            except Exception:                               # noqa: BLE001
                pass
        self.pdf_doc = None
        self._set_page_controls(False)
        self.page_lbl.setText(self._z("page_dash"))

    def paste_image(self):
        qimg = QGuiApplication.clipboard().image()
        if qimg.isNull():
            self.shell.notify(self._z("no_clip"), "error")
            return False
        self._close_pdf()
        self.set_image(qimage_to_bgr(qimg), self._z("img_pasted"))
        return True

    def grab_screen(self):
        win = self.window()
        win.hide()
        QTimer.singleShot(350, self._grab_after_hide)        # give the compositor time to remove our window

    def _grab_after_hide(self):
        win = self.window()
        try:
            shot = grab_desktop()
        except Exception as e:                              # noqa: BLE001
            win.show()
            self._error(self._z("grab_failed_title"), f"{type(e).__name__}: {e}")
            return
        self._snip = ScreenSnip(shot, self._z("grab_hint"), self._grab_done)
        self._snip.show()
        self._snip.activateWindow()
        self._snip.setFocus()

    def _grab_done(self, img):
        win = self.window()
        win.show()
        win.raise_()
        win.activateWindow()
        self._snip = None
        if img is None:
            self.status.setText(self._z("grab_cancelled"))
            return
        self._close_pdf()
        self.set_image(img, self._z("img_captured"))

    # ------------------------------------------------------------------ modes / mouse
    def set_mode(self, mode):
        if mode is not None and self.cv_img is None:
            self._info(self._z("no_image_title"), self._z("no_image"))
            return
        self.mode = mode
        self.view.set_capture(mode is not None)
        labels = {"crop": "mode_crop", "control": "mode_control", "polygon": "mode_polygon"}
        if mode:
            self.status.setText(self._z(labels[mode]))

    def _clamp(self, x, y):
        h, w = self.cv_img.shape[:2]
        return max(0.0, min(float(w), x)), max(0.0, min(float(h), y))

    def _on_press(self, x, y):
        if self.mode == "crop":
            self.crop_start = self._clamp(x, y)
        elif self.mode == "control":
            self.add_control_point(x, y)
        elif self.mode == "polygon":
            self.polygon_px.append((x, y))
            self._redraw()

    def _on_move(self, x, y):
        if self.mode == "crop" and self.crop_start is not None:
            self._redraw(temp_rect=(self.crop_start, self._clamp(x, y)))

    def _on_release(self, x, y):
        if self.mode == "crop" and self.crop_start is not None:
            self.set_crop(self.crop_start, self._clamp(x, y))
            self.crop_start = None

    def set_crop(self, a, b):
        (x0, y0), (x1, y1) = a, b
        xl, xh = sorted((int(x0), int(x1)))
        yl, yh = sorted((int(y0), int(y1)))
        if xh - xl > 5 and yh - yl > 5:
            self.crop_rect = (xl, yl, xh, yh)
        self._redraw()

    def _redraw(self, temp_rect=None):
        sc = self.view.scene()
        for it in self._overlay:
            sc.removeItem(it)
        self._overlay = []
        k = 1.0 / max(1e-6, self.view.transform().m11())        # keep marks the same size on screen

        def pen(color, width=2, dash=False):
            p = QPen(QColor(color), width * k)
            if dash:
                p.setStyle(Qt.PenStyle.DashLine)
            return p

        rect = None
        if temp_rect:
            (x0, y0), (x1, y1) = temp_rect
            rect = QRectF(QPointF(x0, y0), QPointF(x1, y1)).normalized()
        elif self.crop_rect:
            x0, y0, x1, y1 = self.crop_rect
            rect = QRectF(x0, y0, x1 - x0, y1 - y0)
        if rect is not None:
            self._overlay.append(sc.addRect(rect, pen("#00e0ff", dash=True)))
        for i, cp in enumerate(self.control_points, 1):
            r = 5 * k
            self._overlay.append(sc.addEllipse(cp.px - r, cp.py - r, 2 * r, 2 * r, pen("black", 1),
                                               QBrush(QColor("#ffcc00"))))
            self._overlay.append(self._text(f"C{i}", cp.px + 8 * k, cp.py - 18 * k, "#ffcc00", k))
        if self.polygon_px:
            path = QPainterPath(QPointF(*self.polygon_px[0]))
            for x, y in self.polygon_px[1:]:
                path.lineTo(x, y)
            self._overlay.append(sc.addPath(path, pen("#c000ff")))
            if len(self.polygon_px) >= 3:
                (ax, ay), (bx, by) = self.polygon_px[-1], self.polygon_px[0]
                self._overlay.append(sc.addLine(ax, ay, bx, by, pen("#c000ff", dash=True)))
            for i, (x, y) in enumerate(self.polygon_px, 1):
                r = 4 * k
                self._overlay.append(sc.addEllipse(x - r, y - r, 2 * r, 2 * r, pen("white", 1),
                                                   QBrush(QColor("#c000ff"))))
                self._overlay.append(self._text(str(i), x + 6 * k, y + 2 * k, "#c000ff", k))

    def _text(self, s, x, y, color, k):
        t = self.view.scene().addSimpleText(s)
        t.setBrush(QColor(color))
        t.setScale(k)
        t.setPos(x, y)
        return t

    # ------------------------------------------------------------------ OCR
    def run_ocr(self):
        if self.cv_img is None:
            return self._info(self._z("no_image_title"), self._z("no_image"))
        if not self.crop_rect:
            return self._info(self._z("no_sel_title"), self._z("no_sel"))
        from tools.coordextract.ocr import OCRUnavailable, extract_table
        backs = getattr(self, "_backends", None)
        if backs is None:
            self.load_backends()
            backs = self._backends
        choice = self.backend_combo.currentText()
        backend = choice if choice in backs else None
        if backend:
            self._remember(backend=backend)
        x0, y0, x1, y1 = self.crop_rect
        crop = self.cv_img[y0:y1, x0:x1].copy()
        self.status.setText(self._z("ocr_running"))

        def work(ctx):
            try:
                return extract_table(crop, backend=backend)
            except OCRUnavailable as e:
                raise RuntimeError(str(e)) from None

        self.shell.run(work, self.TOOL + ".ocr", params={"backend": backend, "box": list(self.crop_rect)},
                       on_done=self._ocr_done)

    def _ocr_done(self, result):
        self.ocr_table.setRowCount(0)
        for r in result.rows:
            self._append(self.ocr_table, (r.label, _fmt(r.x), _fmt(r.y)))
        self.status.setText(self._z("ocr_done", backend=result.backend, n=len(result.rows)))
        if not result.rows:
            self._info(self._z("ocr_no_rows_title"),
                       self._z("ocr_no_rows", raw=(result.raw_text[:800] or self._z("raw_empty"))))

    # ------------------------------------------------------------------ tables
    @staticmethod
    def _append(table, values):
        r = table.rowCount()
        table.insertRow(r)
        for c, v in enumerate(values):
            it = QTableWidgetItem(str(v))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(r, c, it)

    @staticmethod
    def rows_of(table):
        out = []
        for r in range(table.rowCount()):
            out.append(tuple((table.item(r, c).text() if table.item(r, c) else "")
                             for c in range(table.columnCount())))
        return out

    def add_row(self):
        self._append(self.ocr_table, ("", "", ""))
        self.ocr_table.scrollToBottom()

    @staticmethod
    def _selected_rows(table):
        return sorted({i.row() for i in table.selectedIndexes()}, reverse=True)

    def _delete_rows(self, table):
        for r in self._selected_rows(table):
            table.removeRow(r)

    # ------------------------------------------------------------------ geo-reference
    def add_control_point(self, px, py, xy=None):
        from tools.coordextract.georef import ControlPoint
        xy = xy or self._ask_xy(px, py)
        if xy is None:
            return
        X, Y = xy
        self.control_points.append(ControlPoint(px=px, py=py, X=X, Y=Y))
        self._append(self.cp_table, (f"{px:.0f}", f"{py:.0f}", _fmt(X), _fmt(Y)))
        self._redraw()
        self._refit()

    def _refit(self):
        from tools.coordextract.georef import GeoReferenceError, fit_affine
        if len(self.control_points) < 2:
            self.model = None
            self.fit_lbl.setText(self._z("fit_need") if self.control_points else self._z("fit_none"))
            return
        try:
            self.model = fit_affine(self.control_points)
        except GeoReferenceError as e:
            self.model = None
            self.fit_lbl.setText(self._z("fit_error", e=e))
            return
        note = self._z("fit_exact") if self.model.n_points == 2 else self._z("fit_rmse", v=self.model.rmse)
        self.fit_lbl.setText(self._z("fit_ok", n=self.model.n_points, note=note))

    def delete_control_points(self):
        rows = self._selected_rows(self.cp_table)
        for r in rows:
            del self.control_points[r]
            self.cp_table.removeRow(r)
        if rows:
            self._redraw()
            self._refit()

    def clear_polygon(self):
        self.polygon_px.clear()
        self.geo_table.setRowCount(0)
        self.area_lbl.setText(self._z("area_none"))
        self._redraw()

    def compute_geo(self):
        from tools.coordextract.georef import polygon_area
        if self.model is None:
            return self._info(self._z("no_fit_title"), self._z("no_fit"))
        if not self.polygon_px:
            return self._info(self._z("no_poly_title"), self._z("no_poly"))
        world = self.model.apply_many(self.polygon_px)
        self.geo_table.setRowCount(0)
        for i, (X, Y) in enumerate(world, 1):
            self._append(self.geo_table, (i, _fmt(X), _fmt(Y)))
        if len(world) >= 3:
            a = polygon_area(world)
            self.area_lbl.setText(self._z("area_val", u=a, ha=a / 10000))
        else:
            self.area_lbl.setText(self._z("area_need"))
        self.status.setText(self._z("computed", n=len(world)))

    # ------------------------------------------------------------------ export
    def export(self, table, fmt, path=None):
        from tools.coordextract import export as ex
        from tools.xlsx_format import FileLockedError
        rows = self.rows_of(table)
        if not rows:
            self._info(self._z("nothing_exp_title"), self._z("nothing_exp"))
            return None
        ext = {"csv": ".csv", "json": ".json", "xlsx": ".xlsx"}[fmt]
        path = path or self._save_name("{} (*{})".format(fmt.upper(), ext), ext)
        if not path:
            return None
        note = self._z("geo_note") if table is self.geo_table and self.model is not None else None
        try:
            if fmt == "csv":
                ex.rows_to_csv(path, rows)
            elif fmt == "xlsx":
                ex.rows_to_xlsx(path, rows, note=note)
            else:
                ex.rows_to_json(path, rows, extra={"crs_note": note} if note else None)
        except FileLockedError:
            self._error(self._z("export_failed"), self._z("file_locked"))
            return None
        except Exception as e:                              # noqa: BLE001
            self._error(self._z("export_failed"), str(e))
            return None
        if fmt == "xlsx":
            self._last_xlsx = path
        self._last_dir = os.path.dirname(path)
        self._remember(last_dir=self._last_dir)
        msg = self._z("saved", name=os.path.basename(path))
        self.status.setText(msg)
        self.shell.notify(msg)
        return path

    def format_excel(self, path=None):
        from tools.coordextract import export as ex
        from tools.xlsx_format import FileLockedError
        path = path or self._open_name(self._z("pick_xlsx"), "Excel (*.xlsx)", self._last_xlsx)
        if not path:
            return None
        if not self._confirm(self._z("format_confirm", name=os.path.basename(path))):
            return None
        try:
            n_busy = ex.format_target_filled(path)
        except Exception as e:                              # noqa: BLE001
            self._error(self._z("format_failed"), str(e))
            return None
        if n_busy and not self._confirm(self._z("format_busy", n=n_busy)):
            return None
        try:
            _saved, n = ex.format_xlsx(path)
        except FileLockedError:
            self._error(self._z("format_failed"), self._z("file_locked"))
            return None
        except Exception as e:                              # noqa: BLE001
            self._error(self._z("format_failed"), str(e))
            return None
        if n == 0:
            self._info(self._z("format_failed"), self._z("format_empty"))
            return 0
        self._last_xlsx = path
        msg = self._z("format_done", n=n)
        self.status.setText(msg)
        self.shell.notify(msg)
        return n
