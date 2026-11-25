"""Light / dark themes as one Qt stylesheet built from a palette."""

PALETTES = {
    "light": {"window": "#f4f5f7", "surface": "#ffffff", "side": "#eceff3", "text": "#1f2328",
              "muted": "#656d76", "accent": "#1a7f64", "accent_text": "#ffffff", "border": "#d0d7de",
              "hover": "#e2e8ee", "select": "#d4efe6", "danger": "#cf222e", "warn": "#9a6700"},
    "dark": {"window": "#0d1117", "surface": "#161b22", "side": "#11161d", "text": "#e6edf3",
             "muted": "#8b949e", "accent": "#3fb68b", "accent_text": "#06231a", "border": "#30363d",
             "hover": "#1f2630", "select": "#1b3a30", "danger": "#ff7b72", "warn": "#d29922"},
}


def palette(name):
    return PALETTES.get(name, PALETTES["light"])


def stylesheet(name):
    p = palette(name)
    return """
QWidget {{ background: {window}; color: {text}; font-size: 13px; }}
QMainWindow, QStackedWidget, QScrollArea {{ background: {window}; }}
#sidebar, #sidebar QWidget {{ background: {side}; }}
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QTableWidget, QListWidget, QTreeWidget {{
    background: {surface}; border: 1px solid {border}; border-radius: 6px; padding: 4px; }}
QTreeWidget, QListWidget {{ padding: 2px; }}
QTreeWidget::item {{ padding: 5px 4px; border-radius: 4px; }}
QTreeWidget::item:hover {{ background: {hover}; }}
QTreeWidget::item:selected {{ background: {select}; color: {text}; }}
QPushButton {{ background: {surface}; border: 1px solid {border}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ background: {hover}; }}
QPushButton:disabled {{ color: {muted}; }}
QPushButton#primary {{ background: {accent}; color: {accent_text}; border: none; font-weight: 600; }}
QPushButton#primary:disabled {{ background: {border}; color: {muted}; }}
QLabel#title {{ font-size: 20px; font-weight: 600; background: transparent; }}
QLabel#muted, QLabel#desc {{ color: {muted}; background: transparent; }}
QLabel#warn {{ color: {warn}; background: transparent; }}
QLabel#toast {{ background: {accent}; color: {accent_text}; border-radius: 8px; padding: 10px 16px; font-weight: 600; }}
QLabel#toast[kind="error"] {{ background: {danger}; color: #ffffff; }}
QMenuBar, QMenu, QStatusBar {{ background: {surface}; }}
QMenu::item:selected {{ background: {select}; }}
QProgressBar {{ border: 1px solid {border}; border-radius: 5px; text-align: center; background: {surface}; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}
QHeaderView::section {{ background: {side}; border: none; padding: 4px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 4px; min-width: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QToolTip {{ background: {surface}; color: {text}; border: 1px solid {border}; }}
QRadioButton::indicator {{ width: 12px; height: 12px; border-radius: 7px; border: 1px solid {muted}; background: {surface}; }}
QRadioButton::indicator:checked {{ border: 4px solid {accent}; width: 6px; height: 6px; background: {surface}; }}
QRadioButton::indicator:disabled {{ border-color: {border}; }}
QCheckBox::indicator {{ width: 12px; height: 12px; border-radius: 3px; border: 1px solid {muted}; background: {surface}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QCheckBox::indicator:disabled {{ border-color: {border}; }}
""".format(**p)
