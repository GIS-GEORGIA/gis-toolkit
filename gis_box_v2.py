#!/usr/bin/env python
"""GIS_BOX V2 - modern PySide6 interface. The classic app (gis_box.py) is untouched and still works.

    python gis_box_v2.py            # start the V2 window
    python gis_box_v2.py --selftest # build the window offscreen, print OK, exit (CI / diagnostics)
"""
import os
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is not installed.  pip install PySide6   (see requirements-optional.txt)", file=sys.stderr)
        return 2
    from v2.main_window import MainWindow
    from v2.settings import Settings

    from tools import update_manager
    update_manager.cleanup_on_start()                  # removes *.gbold-* leftovers of a previous update (frozen only)
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("GIS_BOX")
    win = MainWindow(Settings())
    if "--selftest" in argv:
        print("OK GIS_BOX V2 window built:", win.windowTitle())
        return 0
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
