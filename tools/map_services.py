# -*- coding: utf-8 -*-
"""რუკის სერვისების საცნობარო ხელსაწყო.

GIS tile/WMS სერვისების URL-ები (Google basemaps, ორთოფოტო) — ArcMap/QGIS-ში
გადასაკოპირებლად. სია იკითხება რეპოს ძირის ``map_services.txt``-იდან
(ფორმატი: სახელის ხაზი, შემდეგ URL-ის ხაზი) — ახლის დამატება ფაილის
რედაქტირებით, კოდის შეხების გარეშე.
"""
import os
import tkinter as tk
from tkinter import ttk

from tools.base import ToolFrame
from tools.platform_utils import UI_FONT, MONO_FONT
from tools.tooltip import add_tip

# map_services.txt — user-editable, ჩაშენებული ნაგულისხმევით. ჯერ ჩასაწერ
# კონფიგ-საქაღალდეს ვამოწმებთ, თუ იქ არაა — ბანდლის ნაგულისხმევს.
from tools.apppaths import config_read_path
SERVICES_FILE = config_read_path("map_services.txt")

EXTRA_SERVICES = [
    ("NAPR ორთოფოტო 2023 (WMS)",
     "https://mp.napr.gov.ge/ORTHO_2023_BLK2/ows?service=wms&version=1.3.0&request=GetCapabilities"),
]

# ---- თარგმანები ------------------------------------------------------------
MTR = {
    "heading": {"en": "Map services", "ka": "რუკის სერვისები"},
    "desc":    {"en": "tile / WMS service URLs (Google basemaps, ortho) to copy into "
                      "ArcMap / QGIS. Some services may require VPN / access. "
                      "Edit map_services.txt to add your own.",
                "ka": "tile / WMS სერვისების URL-ები (Google basemaps, ორთოფოტო) — "
                      "ArcMap / QGIS-ში გადასაკოპირებლად. ზოგი სერვისი მოითხოვს "
                      "VPN-ს / წვდომას. ახლის დასამატებლად შეასწორე map_services.txt."},
    "copy":    {"en": "Copy", "ka": "კოპირება"},
    "tip_copy": {"en": "Copy this URL to the clipboard — paste it into ArcMap / QGIS "
                       "as a new tile / WMS layer.",
                 "ka": "URL-ის კოპირება — ჩასვი ArcMap / QGIS-ში ახალ tile / WMS "
                       "შრედ."},
    "empty":   {"en": "map_services.txt not found or empty.",
                "ka": "map_services.txt ვერ მოიძებნა ან ცარიელია."},
}


def _load_services(path=SERVICES_FILE):
    services, name = [], None
    if os.path.exists(path):
        for raw in open(path, encoding="utf-8"):
            line = raw.strip()
            if not line or line.lower().startswith("services"):
                name = None
                continue
            if line.startswith("http"):
                if name:
                    services.append((name, line))
                    name = None
            else:
                name = line
    return services + EXTRA_SERVICES


class MapServicesTool(ToolFrame):
    tid = "map_services"
    CATALOG = MTR

    def build(self):
        pal = self.app.palette
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        ttk.Label(self, text=self.tr("heading"),
                  font=(UI_FONT, 13, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Label(self, text=self.tr("desc"), foreground=pal["muted"],
                  wraplength=640, justify="left").grid(
            row=1, column=0, sticky="w", pady=(0, 12))

        # სქროლადი სია
        wrap = ttk.Frame(self)
        wrap.grid(row=2, column=0, sticky="nsew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        canvas = tk.Canvas(wrap, bg=pal["bg"], highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=vsb.set)

        inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(win, width=e.width))
        inner.columnconfigure(0, weight=1)

        services = _load_services()
        if not services:
            ttk.Label(inner, text=self.tr("empty"),
                      foreground=pal["muted"]).grid(row=0, column=0,
                                                    sticky="w", padx=2, pady=4)
            return
        for i, (name, url) in enumerate(services):
            self._row(inner, i, name, url, pal)

    def _row(self, parent, i, name, url, pal):
        box = ttk.LabelFrame(parent, text=name, padding=8)
        box.grid(row=i, column=0, sticky="ew", padx=2, pady=4)
        box.columnconfigure(0, weight=1)
        var = tk.StringVar(value=url)
        ent = ttk.Entry(box, textvariable=var, font=(MONO_FONT, 9))
        ent._var = var                                # რეფ. GC-ს გადასარჩენად
        ent.bind("<Key>", lambda e: "break")          # read-only, მაგრამ ჩანს
        ent.grid(row=0, column=0, sticky="ew")
        add_tip(ttk.Button(box, text="📋  " + self.tr("copy"), width=12,
                           command=lambda u=url: self._copy(u)),
                self.tr("tip_copy")).grid(row=0, column=1, padx=(8, 0))

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.log(f"📋  {text}")
