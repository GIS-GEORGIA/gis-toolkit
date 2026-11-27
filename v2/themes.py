"""Light / dark themes: one palette per theme -> a Qt stylesheet and a matching QPalette.

The stylesheet deliberately does NOT paint every QWidget (``QWidget { background: ... }``): containers stay
transparent, so group boxes, cards and the sidebar can have their own surface colour without children painting
over it. Widgets the stylesheet does not reach (scroll-area viewports, message boxes, native dialogs) take their
colours from the QPalette set by :func:`apply`."""

PALETTES = {
    "light": {"window": "#f4f6f8", "surface": "#ffffff", "surface_alt": "#f8fafb", "side": "#eaeef2",
              "text": "#1f2328", "muted": "#59636e", "accent": "#1a7f64", "accent_hover": "#176f58",
              "accent_pressed": "#125a47", "accent_text": "#ffffff", "border": "#d0d7de",
              "border_strong": "#afb8c1", "hover": "#e3e9ee", "pressed": "#d5dde4", "select": "#d4efe6",
              "focus": "#1a7f64", "danger": "#cf222e", "danger_hover": "#a40e26", "warn": "#9a6700",
              "ok": "#1a7f37", "shadow": "#dfe4e9", "disabled_bg": "#eef1f4"},
    "dark": {"window": "#0d1117", "surface": "#161b22", "surface_alt": "#1b2129", "side": "#11161d",
             "text": "#e6edf3", "muted": "#9198a1", "accent": "#3fb68b", "accent_hover": "#52c79c",
             "accent_pressed": "#2f9a74", "accent_text": "#06231a", "border": "#30363d",
             "border_strong": "#484f58", "hover": "#1f2630", "pressed": "#262e39", "select": "#1b3a30",
             "focus": "#3fb68b", "danger": "#ff7b72", "danger_hover": "#ffa198", "warn": "#d29922",
             "ok": "#3fb950", "shadow": "#010409", "disabled_bg": "#161b22"},
}

# Badge colours per tool category (readable with white text in both themes).
CATEGORY_COLORS = {"crs": "#2f6fb5", "analysis": "#8a4fbf", "data": "#1a7f64", "search": "#c4622d",
                   "system": "#5b6673"}


def palette(name):
    return PALETTES.get(name, PALETTES["light"])


def category_color(cat_id):
    return CATEGORY_COLORS.get(cat_id, "#5b6673")


def stylesheet(name):
    p = palette(name)
    return """
QWidget {{ color: {text}; font-size: 13px; }}
QMainWindow, QDialog, QStackedWidget {{ background: {window}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
QAbstractScrollArea {{ background: transparent; }}

/* ---- sidebar ---- */
#sidebar {{ background: {side}; border-right: 1px solid {border}; }}
#sidebar QTreeWidget {{ background: transparent; border: none; padding: 0; }}
#sidebar QTreeWidget::item {{ padding: 6px 6px; margin: 1px 0; border-radius: 6px; }}
#sidebar QTreeWidget::item:hover {{ background: {hover}; }}
#sidebar QTreeWidget::item:selected {{ background: {select}; color: {text}; }}
QLabel#brand {{ font-size: 18px; font-weight: 700; }}

/* ---- inputs ---- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {surface}; border: 1px solid {border}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {accent}; selection-color: {accent_text}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ min-height: 20px; }}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
QPlainTextEdit:hover, QTextEdit:hover {{ border-color: {border_strong}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {focus}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QPlainTextEdit:disabled, QTextEdit:disabled {{ background: {disabled_bg}; color: {muted}; }}
QLineEdit[readOnly="true"] {{ background: {surface_alt}; }}
QComboBox QAbstractItemView {{ background: {surface}; border: 1px solid {border}; outline: 0;
    selection-background-color: {select}; selection-color: {text}; }}

/* ---- lists / tables ---- */
QTableWidget, QTableView, QListWidget, QTreeWidget, QTreeView {{
    background: {surface}; border: 1px solid {border}; border-radius: 6px; padding: 2px;
    alternate-background-color: {surface_alt}; gridline-color: {border}; outline: 0; }}
QTreeWidget::item, QListWidget::item {{ padding: 4px; border-radius: 4px; }}
QTreeWidget::item:hover, QListWidget::item:hover, QTableWidget::item:hover {{ background: {hover}; }}
QTreeWidget::item:selected, QListWidget::item:selected, QTableWidget::item:selected {{
    background: {select}; color: {text}; }}
QHeaderView::section {{ background: {surface_alt}; color: {muted}; border: none;
    border-bottom: 1px solid {border}; padding: 5px 6px; font-weight: 600; }}
QTableCornerButton::section {{ background: {surface_alt}; border: none; }}

/* ---- buttons ---- */
QPushButton {{ background: {surface}; border: 1px solid {border}; border-radius: 6px; padding: 6px 14px;
    min-height: 18px; }}
QPushButton:hover {{ background: {hover}; border-color: {border_strong}; }}
QPushButton:pressed {{ background: {pressed}; }}
QPushButton:focus {{ border: 1px solid {focus}; }}
QPushButton:disabled {{ background: {disabled_bg}; color: {muted}; border-color: {border}; }}
QPushButton:checked {{ background: {select}; border-color: {accent}; }}
QPushButton#primary {{ background: {accent}; color: {accent_text}; border: 1px solid {accent}; font-weight: 600; }}
QPushButton#primary:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton#primary:pressed {{ background: {accent_pressed}; }}
QPushButton#primary:disabled {{ background: {border}; color: {muted}; border-color: {border}; }}
QPushButton#danger {{ background: transparent; color: {danger}; border: 1px solid {danger}; }}
QPushButton#danger:hover {{ background: {danger}; color: #ffffff; }}
QPushButton#danger:disabled {{ color: {muted}; border-color: {border}; background: transparent; }}
QPushButton#ghost {{ background: transparent; border: 1px solid transparent; color: {muted}; }}
QPushButton#ghost:hover {{ background: {hover}; color: {text}; }}
QPushButton#ghost:checked {{ color: {accent}; background: transparent; }}
QPushButton#ghost:checked:hover {{ background: {hover}; }}
QPushButton#card {{ background: {surface}; border: 1px solid {border}; border-radius: 10px; padding: 0;
    text-align: left; }}
QPushButton#card:hover {{ border-color: {accent}; background: {surface_alt}; }}
QPushButton#card:pressed {{ background: {pressed}; }}
QPushButton#card:focus {{ border: 2px solid {focus}; }}
QPushButton#chip {{ border-radius: 14px; padding: 4px 12px; background: {surface}; }}
QPushButton#chip:hover {{ border-color: {accent}; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 3px; }}
QToolButton:hover {{ background: {hover}; border-color: {border}; }}

/* ---- group boxes / tabs / splitters ---- */
QGroupBox {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; margin-top: 14px;
    padding: 12px 10px 10px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 4px;
    color: {text}; font-weight: 600; }}
QGroupBox:disabled {{ color: {muted}; }}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 8px; top: -1px; background: {surface}; }}
QTabBar::tab {{ background: transparent; color: {muted}; border: none; border-bottom: 2px solid transparent;
    padding: 7px 14px; margin-right: 2px; }}
QTabBar::tab:selected {{ color: {text}; font-weight: 600; border-bottom: 2px solid {accent}; }}
QTabBar::tab:hover:!selected {{ color: {text}; background: {hover}; border-radius: 6px; }}
QSplitter::handle {{ background: {border}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QSplitter::handle:hover {{ background: {accent}; }}

/* ---- labels ---- */
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 20px; font-weight: 600; }}
QLabel#section {{ font-size: 14px; font-weight: 600; }}
QLabel#cardTitle {{ font-weight: 600; }}
QLabel#muted, QLabel#desc {{ color: {muted}; }}
QLabel#caps {{ color: {muted}; font-size: 12px; font-weight: 600; letter-spacing: 0.3px; }}
QLabel#warn {{ color: {warn}; }}
QLabel#error {{ color: {danger}; }}
QLabel#accent {{ color: {accent}; }}
QLabel#toast {{ background: {accent}; color: {accent_text}; border-radius: 8px; padding: 10px 16px;
    font-weight: 600; }}
QLabel#toast[kind="error"] {{ background: {danger}; color: #ffffff; }}
QFrame#errorPanel {{ background: {surface}; border: 1px solid {danger}; border-radius: 8px; }}
QFrame#hline {{ background: {border}; max-height: 1px; border: none; }}

/* ---- check / radio ---- */
QCheckBox, QRadioButton {{ spacing: 7px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {border_strong};
    background: {surface}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QCheckBox::indicator:indeterminate {{ background: {border_strong}; border-color: {border_strong}; }}
QRadioButton::indicator:checked {{ border: 4px solid {accent}; width: 8px; height: 8px; }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: {border}; background: {disabled_bg}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {muted}; }}

/* ---- menus, status bar, progress, tooltips, scroll bars ---- */
QMenuBar {{ background: {surface}; border-bottom: 1px solid {border}; }}
QMenuBar::item {{ padding: 5px 10px; background: transparent; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {hover}; }}
QMenu {{ background: {surface}; border: 1px solid {border}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {select}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}
QStatusBar {{ background: {surface}; border-top: 1px solid {border}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ padding: 0 6px; }}
QProgressBar {{ border: 1px solid {border}; border-radius: 5px; text-align: center; background: {surface_alt};
    min-height: 12px; font-size: 11px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}
QToolTip {{ background: {surface}; color: {text}; border: 1px solid {border}; padding: 5px 7px; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 3px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 3px; min-width: 28px; }}
QScrollBar::handle:horizontal:hover {{ background: {muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
""".format(**p)


def qpalette(name):
    """QPalette with the theme colours, for widgets/dialogs the stylesheet does not style."""
    from PySide6.QtGui import QColor, QPalette
    p = palette(name)
    pal = QPalette()
    roles = QPalette.ColorRole
    for role, key in ((roles.Window, "window"), (roles.WindowText, "text"), (roles.Base, "surface"),
                      (roles.AlternateBase, "surface_alt"), (roles.Text, "text"), (roles.Button, "surface"),
                      (roles.ButtonText, "text"), (roles.ToolTipBase, "surface"), (roles.ToolTipText, "text"),
                      (roles.Highlight, "accent"), (roles.HighlightedText, "accent_text"),
                      (roles.PlaceholderText, "muted"), (roles.Link, "accent"), (roles.Mid, "border"),
                      (roles.Midlight, "hover"), (roles.Dark, "border_strong")):
        pal.setColor(role, QColor(p[key]))
    for role in (roles.WindowText, roles.Text, roles.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(p["muted"]))
    return pal


def apply(app, name):
    """Apply theme ``name`` to the whole application. Re-applying the theme that is already active is skipped:
    every setPalette / setStyleSheet re-polishes EVERY live widget, which is what made opening a second window
    or re-selecting the same theme slow."""
    css = stylesheet(name)
    if app.property("gisbox_theme") == name and app.styleSheet() == css:
        return False
    # Measured with all 14 tool pages open: replacing one stylesheet with another directly took ~0.5 s,
    # clearing it first and then setting palette + stylesheet ~0.12 s (same result).
    if app.styleSheet():
        app.setStyleSheet("")
    app.setPalette(qpalette(name))
    app.setStyleSheet(css)
    app.setProperty("gisbox_theme", name)
    return True
