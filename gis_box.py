# -*- coding: utf-8 -*-
"""
GIS_BOX — პატარა GIS ინსტრუმენტების კრებული / a small collection of GIS tools.

გაფართოებადი / extensible: ახალი ინსტრუმენტისთვის შექმენი ToolFrame-ის მემკვიდრე
კლასი და დაამატე TOOLS სიაში.
"""

import os
import re
import sys
import json
import glob
import shutil
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# tools/ პაკეტი GIS_BOX-ის ძირშია — დავრწმუნდეთ, რომ იმპორტირებადია მაშინაც,
# როცა აპლიკაცია სხვა სამუშაო დირექტორიიდან იშვება.
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# ---- ბილიკები / paths ------------------------------------------------------
DEFAULT_SHP_DIR = os.path.join(APP_DIR, "shp")
SETTINGS_FILE = os.path.join(APP_DIR, "gis_box_settings.json")

# ---- თარგმანები / translations --------------------------------------------
LANGS = {"en": "English", "ka": "ქართული"}

TR = {
    "tools":        {"en": "Tools",                "ka": "ინსტრუმენტები"},
    "log":          {"en": "Log",                  "ka": "ლოგი"},
    "log_clear":    {"en": "Clear",                "ka": "გასუფთავება"},
    "log_save":     {"en": "Save .txt",            "ka": "შენახვა .txt"},
    "log_empty":    {"en": "The log is empty.",     "ka": "ლოგი ცარიელია."},
    "log_saved":    {"en": "Log saved:",           "ka": "ლოგი შენახულია:"},
    "log_title":    {"en": "Save log",             "ka": "ლოგის შენახვა"},
    "language":     {"en": "Language",             "ka": "ენა"},
    "theme":        {"en": "Theme",                "ka": "თემა"},
    "light":        {"en": "Light",                "ka": "ღია"},
    "dark":         {"en": "Dark",                 "ka": "მუქი"},

    # TemplateCopier
    "tc_title":     {"en": "Template Copy",        "ka": "შაბლონის კოპირება"},
    "tc_heading":   {"en": "Copy template shapefile",
                     "ka": "შაბლონი შეიპფაილის კოპირება"},
    "tc_desc":      {"en": "Pick the UTM zone(s) and a target folder. "
                           "All sidecar files (.shp/.shx/.dbf/.prj/…) are copied.",
                     "ka": "აირჩიე UTM ზონა(ები) და სამიზნე დირექტორია. "
                           "შეიპფაილის ყველა თანმხლები ფაილი (.shp/.shx/.dbf/.prj/…) დაკოპირდება."},
    "tc_source":    {"en": "Template (source) folder:",
                     "ka": "შაბლონის (წყარო) საქაღალდე:"},
    "tc_zone_box":  {"en": "UTM zone",             "ka": "UTM ზონა"},
    "tc_layer_box": {"en": "Template",             "ka": "შაბლონი"},
    "tc_zone":      {"en": "Zone {z}",             "ka": "ზონა {z}"},
    "tc_notfound":  {"en": "not found",            "ka": "ვერ მოიძებნა"},
    "tc_target":    {"en": "Target folder:",       "ka": "სამიზნე დირექტორია:"},
    "tc_hint":      {"en": "Each click adds a new copy with an incrementing suffix "
                           "(…_1, …_2, …).",
                     "ka": "ყოველი დაწკაპუნება ამატებს ახალ ასლს ზრდადი სუფიქსით "
                           "(…_1, …_2, …)."},
    "tc_copy":      {"en": "Copy",                 "ka": "კოპირება"},
    "tc_remember":  {"en": "💾 Remember folder",   "ka": "💾 საქაღალდის დამახსოვრება"},
    "tc_remember_all": {"en": "for all tools",     "ka": "ყველა ხელსაწყოსთვის"},
    "tc_tip_source":{"en": "Folder that holds the template shapefiles.",
                     "ka": "საქაღალდე, სადაც შაბლონი shapefile-ებია."},
    "tc_tip_dest":  {"en": "Where to copy the template to.",
                     "ka": "სად დაკოპირდეს შაბლონი."},
    "tc_tip_copy":  {"en": "Copy the template with all sidecar files (auto-numbered).",
                     "ka": "შაბლონის კოპირება ყველა თანმხლები ფაილით (ავტო-ნუმერაციით)."},
    "tc_tip_remember": {"en": "Remember the target folder for next time.",
                        "ka": "სამიზნე საქაღალდის დამახსოვრება მომავლისთვის."},
    "tc_tip_remember_all": {"en": "Use one saved folder for every copy tool.",
                            "ka": "ერთი შენახული საქაღალდე ყველა კოპირ-ხელსაწყოსთვის."},
    "tc_saved":     {"en": "Folder saved — it will be remembered next time.",
                     "ka": "საქაღალდე შენახულია — მომდევნო გაშვებაზეც დაიმახსოვრდება."},
    "browse":       {"en": "Browse…",              "ka": "დათვალიერება…"},
    "warn_zone":    {"en": "Select at least one zone.",
                     "ka": "აირჩიე მინიმუმ ერთი ზონა."},
    "warn_dest":    {"en": "Specify a target folder.",
                     "ka": "მიუთითე სამიზნე დირექტორია."},
    "err_mkdir":    {"en": "Could not create folder:",
                     "ka": "დირექტორია ვერ შეიქმნა:"},
    "made_dir":     {"en": "Created folder:",      "ka": "შეიქმნა დირექტორია:"},
    "skip_exists":  {"en": "skipped (exists):",    "ka": "გამოტოვდა (არსებობს):"},
    "no_tmpl":      {"en": "template not found for zone",
                     "ka": "შაბლონი ვერ მოიძებნა ზონისთვის"},
    "done":         {"en": "done",                 "ka": "დასრულდა"},
    "res_copied":   {"en": "Copied",               "ka": "დაკოპირდა"},
    "res_skipped":  {"en": "Skipped",              "ka": "გამოტოვდა"},
    "files":        {"en": "files",                "ka": "ფაილი"},

    # ჩაშენებული ხელსაწყოები / bundled tools
    "parcel_name":  {"en": "Parcel search",        "ka": "ნაკვეთის ძებნა"},
    "coord_name":   {"en": "Coord. extractor",     "ka": "კოორდ. ამომღები"},
    "rename_name":  {"en": "Rename → Latin",       "ka": "სახელების გადარქმევა"},
    "shpcoord_name":{"en": "Shp → coordinates",     "ka": "Shp → კოორდინატები"},
    "gdb2pg_name":  {"en": "GDB → PostGIS",         "ka": "GDB → PostGIS"},
    "tool_load_err":{"en": "This tool could not be loaded.",
                     "ka": "ეს ინსტრუმენტი ვერ ჩაიტვირთა."},
    "tool_dep_hint":{"en": "A required package is probably missing. Install:",
                     "ka": "სავარაუდოდ აკლია საჭირო პაკეტი. დააინსტალირე:"},
}

# ---- თემები / theme palettes ----------------------------------------------
THEMES = {
    "light": {
        "bg": "#f4f4f5", "panel": "#e9e9ec", "fg": "#1a1a1a",
        "muted": "#666666", "field_bg": "#ffffff", "field_fg": "#1a1a1a",
        "log_bg": "#ffffff", "log_fg": "#1a1a1a", "select": "#cfe0ff",
    },
    "dark": {
        "bg": "#1e1e20", "panel": "#26262a", "fg": "#e6e6e6",
        "muted": "#9a9a9a", "field_bg": "#2d2d31", "field_fg": "#e6e6e6",
        "log_bg": "#141416", "log_fg": "#d4d4d4", "select": "#33456b",
    },
}


# ---- ბაზისური ინსტრუმენტი / base tool -------------------------------------
# ToolFrame გატანილია tools/base.py-ში, რომ ხელსაწყოებმაც და აქაც ერთი კლასი
# გამოიყენონ (gis_box __main__-ის ხელახლა იმპორტის გარეშე).
from tools.base import ToolFrame
from tools.i18n import translate
from tools.tooltip import add_tip


# ---- ინსტრუმენტი: შაბლონის კოპირება (პარამეტრიზებული) ---------------------
class TemplateCopier(ToolFrame):
    def __init__(self, master, app, config):
        self.config = config
        self.tid = config["id"]
        self.templates = config["templates"]
        super().__init__(master, app)

    def title(self):
        return self.config["name_" + self.app.lang]

    def _state(self):
        return self.app.tool_state.setdefault(self.tid, {})

    def build(self):
        pal = self.app.palette
        st = self._state()

        ttk.Label(self, text=self.title(),
                  font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

        ttk.Label(self, text=self.t("tc_desc"), foreground=pal["muted"],
                  wraplength=520, justify="left").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))

        # წყარო (შაბლონის) საქაღალდე
        ttk.Label(self, text=self.t("tc_source")).grid(
            row=2, column=0, columnspan=3, sticky="w")
        self.src_var = tk.StringVar(value=self.app.source_dir)
        ttk.Entry(self, textvariable=self.src_var, width=52).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        add_tip(ttk.Button(self, text=self.t("browse"), command=self.pick_source),
                self.t("tc_tip_source")).grid(
            row=3, column=2, sticky="ew", padx=(8, 0), pady=(2, 10))

        # ზონები / შაბლონი
        box_key = "tc_zone_box" if self.config.get("zoned", True) else "tc_layer_box"
        self.zone_box = ttk.LabelFrame(self, text=self.t(box_key), padding=10)
        self.zone_box.grid(row=4, column=0, columnspan=3, sticky="ew",
                           pady=(0, 12))
        self.zone_vars = {}
        self._build_zones()

        # სამიზნე — საწყისი გზა: სესია → ამ ხელსაწყოს შენახული → საერთო → ცარიელი
        own_cfg = self.app.get_tool_config(self.tid)
        shared = self.app.get_tool_config("_shared")
        dest_initial = st.get("dest") or own_cfg.get("dest") or shared.get("target") or ""
        ttk.Label(self, text=self.t("tc_target")).grid(
            row=5, column=0, columnspan=3, sticky="w")
        self.dest_var = tk.StringVar(value=dest_initial)
        ttk.Entry(self, textvariable=self.dest_var, width=52).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        add_tip(ttk.Button(self, text=self.t("browse"), command=self.pick_dest),
                self.t("tc_tip_dest")).grid(
            row=6, column=2, sticky="ew", padx=(8, 0), pady=(2, 0))

        ttk.Label(self, text=self.t("tc_hint"), foreground=pal["muted"],
                  wraplength=520, justify="left").grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(10, 12))

        # მოქმედებები: კოპირება + საქაღალდის დამახსოვრება (+ „ყველასთვის“)
        actions = ttk.Frame(self)
        actions.grid(row=8, column=0, columnspan=3, sticky="ew")
        add_tip(ttk.Button(actions, text=self.t("tc_copy"), command=self.do_copy),
                self.t("tc_tip_copy")).pack(side="left")
        add_tip(ttk.Button(actions, text=self.t("tc_remember"), command=self._remember),
                self.t("tc_tip_remember")).pack(side="left", padx=(12, 4))
        self.remember_all_var = tk.BooleanVar(value=False)
        add_tip(ttk.Checkbutton(actions, text=self.t("tc_remember_all"),
                                variable=self.remember_all_var),
                self.t("tc_tip_remember_all")).pack(side="left")

        self.columnconfigure(0, weight=1)

    def _remember(self):
        """სამიზნე საქაღალდის მუდმივად შენახვა (git-ignored პარამეტრებში).

        „ყველასთვის“ მონიშვნისას გზა ინახება საერთო ნაგულისხმევად და ცალკეული
        შაბლონების პირადი override-ები იშლება — ე.ი. ერთი საქაღალდე ყველასთვის.
        სხვა შემთხვევაში ინახება მხოლოდ ამ ხელსაწყოს პირადი გზა.
        """
        dest = self.dest_var.get().strip()
        if self.remember_all_var.get():
            self.app.set_tool_config("_shared", {"target": dest})
            for cfg in TEMPLATE_SETS:
                tc = self.app.get_tool_config(cfg["id"])
                if tc.get("dest"):
                    tc.pop("dest", None)
                    self.app.set_tool_config(cfg["id"], tc)
        else:
            self.app.set_tool_config(self.tid, {"dest": dest})
        self.save_state()
        messagebox.showinfo("GIS_BOX", self.t("tc_saved"))

    def _build_zones(self):
        for w in self.zone_box.winfo_children():
            w.destroy()
        self.zone_vars.clear()
        st_zones = self._state().get("zones", {})
        zoned = self.config.get("zoned", True)
        single = len(self.templates) == 1
        for i, (zone, base) in enumerate(self.templates.items()):
            exists = bool(self._files_for(zone))
            # ერთშაბლონიანი ნაკრები ნაგულისხმევად მონიშნულია
            default = st_zones.get(zone, single)
            var = tk.BooleanVar(value=default and exists)
            self.zone_vars[zone] = var
            if zoned:
                label = self.t("tc_zone").format(z=zone) + f"  ({base})"
            else:
                label = base
            if not exists:
                label += f"  — ⚠ {self.t('tc_notfound')}"
            ttk.Checkbutton(self.zone_box, text=label, variable=var,
                            state=("normal" if exists else "disabled")).grid(
                row=i, column=0, sticky="w", pady=2)

    def _files_for(self, zone):
        base = self.templates[zone]
        return glob.glob(os.path.join(self.src_var.get().strip(), base + ".*"))

    def pick_source(self):
        d = filedialog.askdirectory(title=self.t("tc_source"),
                                    initialdir=self.src_var.get() or APP_DIR)
        if d:
            d = os.path.normpath(d)
            self.src_var.set(d)
            self.app.source_dir = d
            self.app.save_settings()
            self._build_zones()

    def pick_dest(self):
        d = filedialog.askdirectory(title=self.t("tc_target"))
        if d:
            self.dest_var.set(os.path.normpath(d))

    def save_state(self):
        st = self._state()
        st["dest"] = self.dest_var.get()
        st["zones"] = {z: v.get() for z, v in self.zone_vars.items()}

    @staticmethod
    def _next_index(dest, base):
        """სამიზნეში ბოლო არსებული base_N-ის მიხედვით შემდეგი ინდექსი."""
        pat = re.compile(re.escape(base) + r"_(\d+)(?:\.|$)", re.IGNORECASE)
        n = 0
        try:
            for f in os.listdir(dest):
                m = pat.match(f)
                if m:
                    n = max(n, int(m.group(1)))
        except OSError:
            pass
        return n + 1

    def do_copy(self):
        zones = [z for z, v in self.zone_vars.items() if v.get()]
        dest = self.dest_var.get().strip()

        if not zones:
            messagebox.showwarning("GIS_BOX", self.t("warn_zone"))
            return
        if not dest:
            messagebox.showwarning("GIS_BOX", self.t("warn_dest"))
            return
        if not os.path.isdir(dest):
            try:
                os.makedirs(dest, exist_ok=True)
                self.log(f"{self.t('made_dir')} {dest}")
            except OSError as e:
                messagebox.showerror("GIS_BOX", f"{self.t('err_mkdir')}\n{e}")
                return

        total = 0
        created = []
        for zone in zones:
            files = self._files_for(zone)
            if not files:
                self.log(f"⚠ {self.t('no_tmpl')} {zone}")
                continue
            base = self.templates[zone]
            idx = self._next_index(dest, base)
            new_base = f"{base}_{idx}"
            for src in files:
                name = os.path.basename(src)
                rest = name[len(base):]          # მაგ. .shp / .shp.xml / .CPG
                dst = os.path.join(dest, new_base + rest)
                try:
                    shutil.copy2(src, dst)
                    self.log(f"✓ {new_base}{rest}")
                    total += 1
                except OSError as e:
                    self.log(f"✗ {new_base}{rest}: {e}")
            created.append(new_base)

        self.log(f"— {self.t('done')}: {', '.join(created)} "
                 f"({self.t('res_copied')} {total} {self.t('files')}) —")
        messagebox.showinfo(
            "GIS_BOX",
            f"{self.t('done')}.\n{self.t('res_copied')}: {', '.join(created)}\n\n{dest}")


# ---- შაბლონების ნაკრებები / template sets (აქ დაამატე ახლები) -------------
# ახალი შაბლონისთვის უბრალოდ დაამატე ერთი ჩანაწერი: id უნიკალური,
# templates-ში ზონა→base-name (გაფართოებების გარეშე).
TEMPLATE_SETS = [
    {"id": "riverbank",
     "name_en": "Riverbank line", "name_ka": "მდინარის ნაპირი",
     "templates": {"37": "riverbank_line37", "38": "riverbank_line38"}},
    {"id": "gas_crossing",
     "name_en": "Gas pipe crossing", "name_ka": "გაზსადენის გადაკვეთა",
     "templates": {"37": "Gas_Pipe_Crossing37", "38": "Gas_Pipe_Crossing38"}},
    {"id": "protzone_crossing",
     "name_en": "Protection zone crossing", "name_ka": "დაცვის ზონების გადაკვეთა",
     "templates": {"37": "Gas_Pipe_ProtZone_Crossing37", "38": "Gas_Pipe_ProtZone_Crossing38"}},
    {"id": "utm_grid",
     "name_en": "UTM grid", "name_ka": "UTM ბადე",
     "zoned": False,
     "templates": {"grid": "Georgia_UTM_37_38_grid"}},
]


# ---- მთავარი აპლიკაცია / main app -----------------------------------------
class GisBoxApp(tk.Tk):
    def __init__(self):
        super().__init__()
        # კლავიატურიდან ქართულის სწორად შეყვანა: Tk-ის system encoding ხშირად
        # cp1252-ია (ქართული → „?“); utf-8-ზე გადაყვანა ასწორებს ყველა ველს.
        try:
            self.tk.call("encoding", "system", "utf-8")
        except tk.TclError:
            pass
        self.title("GIS_BOX")
        self.minsize(860, 560)
        try:                       # ფანჯრის ხატულა (Windows-ზე .ico)
            self.iconbitmap(os.path.join(APP_DIR, "gis_box.ico"))
        except tk.TclError:
            pass

        # settings
        self.lang = "ka"
        self.theme = "light"
        self.source_dir = DEFAULT_SHP_DIR
        # per-tool მუდმივი კონფიგურაცია (მაგ. GDB გზა) — ინახება პარამეტრების
        # ფაილში (git-ignored), ამიტომ სენსიტიური გზები კოდში/რეპოში არ ხვდება.
        self.tool_config = {}
        self.current_tool = 0        # ბოლო არჩეული ხელსაწყო (settings-იდან)
        self.win_geometry = ""       # ბოლო ფანჯრის ზომა/პოზიცია
        self.load_settings()

        # უფრო დიდი ნაგულისხმევი ზომა — ჩაშენებული ხელსაწყოებისთვის (რუკა, ცხრილები);
        # თუ წინა სესიის ზომა შენახულია — ვიყენებთ მას.
        self.geometry(self.win_geometry or "1180x760")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # transient state (rebuild-ს გადაურჩება) — თითო ინსტრუმენტზე id-ით
        self.tool_state = {}
        self.log_lines = []

        # ხელსაწყოების რეესტრი (lazy — frame იქმნება პირველ არჩევაზე)
        self.tool_specs = self._build_tool_specs()

        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.rebuild_ui()

    # --- ხელსაწყოების რეესტრი / tool registry ---
    def _build_tool_specs(self):
        """თითო ჩანაწერი: {name_en, name_ka, factory(master)->ToolFrame}.

        შაბლონის კოპირები + ორი ჩაშენებული ხელსაწყო (ნაკვეთის ძებნა,
        კოორდინატების ამომღები). მძიმე ხელსაწყოები lazy-ად იტვირთება.
        """
        specs = []
        for cfg in TEMPLATE_SETS:
            specs.append({
                "name_en": cfg["name_en"], "name_ka": cfg["name_ka"],
                "factory": (lambda master, cfg=cfg: TemplateCopier(master, self, cfg)),
            })
        specs.append({
            "name_en": TR["parcel_name"]["en"], "name_ka": TR["parcel_name"]["ka"],
            "factory": self._make_parcel_tool,
        })
        specs.append({
            "name_en": TR["coord_name"]["en"], "name_ka": TR["coord_name"]["ka"],
            "factory": self._make_coord_tool,
        })
        specs.append({
            "name_en": TR["rename_name"]["en"], "name_ka": TR["rename_name"]["ka"],
            "factory": self._make_rename_tool,
        })
        specs.append({
            "name_en": TR["shpcoord_name"]["en"], "name_ka": TR["shpcoord_name"]["ka"],
            "factory": self._make_shpcoord_tool,
        })
        specs.append({
            "name_en": TR["gdb2pg_name"]["en"], "name_ka": TR["gdb2pg_name"]["ka"],
            "factory": self._make_gdb2pg_tool,
        })
        return specs

    def _make_parcel_tool(self, master):
        from tools.parcel_search import ParcelSearchTool
        return ParcelSearchTool(master, self)

    def _make_coord_tool(self, master):
        from tools.coord_tool import CoordExtractorTool
        return CoordExtractorTool(master, self)

    def _make_rename_tool(self, master):
        from tools.rename_transliterate import RenameTransliterateTool
        return RenameTransliterateTool(master, self)

    def _make_shpcoord_tool(self, master):
        from tools.shp_coords import ShpCoordsTool
        return ShpCoordsTool(master, self)

    def _make_gdb2pg_tool(self, master):
        from tools.gdb2postgis import Gdb2PostgisTool
        return Gdb2PostgisTool(master, self)

    def _instantiate_tool(self, idx):
        """ხელსაწყოს frame-ის შექმნა; შეცდომისას — მეგობრული error frame."""
        spec = self.tool_specs[idx]
        try:
            return spec["factory"](self.container)
        except Exception as e:
            return self._error_frame(e)

    def _error_frame(self, exc):
        p = self.palette
        frame = ttk.Frame(self.container, padding=20)
        ttk.Label(frame, text=self.t("tool_load_err"),
                  font=("Segoe UI", 13, "bold"), foreground="#c0392b").pack(
            anchor="w", pady=(0, 8))
        ttk.Label(frame, text=self.t("tool_dep_hint")).pack(anchor="w")
        ttk.Label(frame, text="pip install -r requirements.txt",
                  font=("Consolas", 10)).pack(anchor="w", pady=(2, 10))
        box = tk.Text(frame, height=10, wrap="word", font=("Consolas", 9),
                      bg=p["log_bg"], fg=p["log_fg"], relief="flat", borderwidth=0)
        box.insert("1.0", f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}")
        box.configure(state="disabled")
        box.pack(fill="both", expand=True)
        return frame

    # --- თარგმანი ---
    def t(self, key):
        return translate(TR, key, self.lang)

    @property
    def palette(self):
        return THEMES[self.theme]

    # --- პარამეტრები / settings ---
    def load_settings(self):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
            self.lang = s.get("lang", self.lang)
            self.theme = s.get("theme", self.theme)
            self.source_dir = s.get("source_dir", self.source_dir)
            self.tool_config = s.get("tool_config", self.tool_config)
            self.current_tool = s.get("current_tool", self.current_tool)
            self.win_geometry = s.get("geometry", self.win_geometry)
        except (OSError, ValueError):
            pass

    def save_settings(self):
        try:
            geom = self.win_geometry
            try:                       # ცოცხალი ფანჯრის მიმდინარე ზომა/პოზიცია
                if self.winfo_exists():
                    geom = self.geometry()
            except tk.TclError:
                pass
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({"lang": self.lang, "theme": self.theme,
                           "source_dir": self.source_dir,
                           "tool_config": self.tool_config,
                           "current_tool": self.current_tool,
                           "geometry": geom}, f,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _on_close(self):
        """დახურვისას — ფანჯრის ზომა/პოზიცია და ბოლო ხელსაწყო შენახვა."""
        try:
            self.win_geometry = self.geometry()
        except tk.TclError:
            pass
        self.save_settings()
        self.destroy()

    # --- per-tool მუდმივი კონფიგურაცია ---
    def get_tool_config(self, tool_id):
        """დაბრუნებულ dict-ს ცვლილება არ ინახება ავტომატურად — გამოიყენე
        set_tool_config დასამახსოვრებლად."""
        return dict(self.tool_config.get(tool_id, {}))

    def set_tool_config(self, tool_id, data):
        """ხელსაწყოს კონფიგურაციის მუდმივად შენახვა (git-ignored ფაილში)."""
        self.tool_config[tool_id] = dict(data)
        self.save_settings()

    # --- თემის გამოყენება / apply theme to ttk styles ---
    def apply_theme(self):
        p = self.palette
        self.configure(bg=p["bg"])
        s = self.style
        s.configure(".", background=p["bg"], foreground=p["fg"],
                    fieldbackground=p["field_bg"])
        s.configure("TFrame", background=p["bg"])
        s.configure("TLabel", background=p["bg"], foreground=p["fg"])
        s.configure("TLabelframe", background=p["bg"], foreground=p["fg"])
        s.configure("TLabelframe.Label", background=p["bg"], foreground=p["fg"])
        s.configure("TCheckbutton", background=p["bg"], foreground=p["fg"])
        s.map("TCheckbutton",
              background=[("active", p["bg"])],
              foreground=[("disabled", p["muted"])])
        s.configure("TButton", background=p["panel"], foreground=p["fg"])
        s.map("TButton",
              background=[("active", p["select"]), ("pressed", p["select"])])
        s.configure("TEntry", fieldbackground=p["field_bg"],
                    foreground=p["field_fg"], insertcolor=p["fg"])
        s.configure("TCombobox", fieldbackground=p["field_bg"],
                    foreground=p["field_fg"])
        s.map("TCombobox", fieldbackground=[("readonly", p["field_bg"])],
              foreground=[("readonly", p["field_fg"])])

    # --- UI-ის აწყობა / (re)build ---
    def rebuild_ui(self):
        # მიმდინარე ინსტრუმენტის მდგომარეობის შენახვა (თუ frame უკვე აშენებულია)
        cur = getattr(self, "frames", [])
        if cur and 0 <= self.current_tool < len(cur):
            f = cur[self.current_tool]
            if f is not None and hasattr(f, "save_state"):
                try:
                    f.save_state()
                except Exception:
                    pass

        for w in self.winfo_children():
            w.destroy()

        self.apply_theme()
        p = self.palette

        # ზედა ზოლი / top bar
        topbar = ttk.Frame(self, padding=(8, 6))
        topbar.pack(side="top", fill="x")

        ttk.Label(topbar, text=self.t("language")).pack(side="left")
        self.lang_cb = ttk.Combobox(topbar, width=10, state="readonly",
                                    values=list(LANGS.values()))
        self.lang_cb.set(LANGS[self.lang])
        self.lang_cb.pack(side="left", padx=(4, 16))
        self.lang_cb.bind("<<ComboboxSelected>>", self.on_lang)

        ttk.Label(topbar, text=self.t("theme")).pack(side="left")
        self.theme_cb = ttk.Combobox(topbar, width=10, state="readonly",
                                     values=[self.t("light"), self.t("dark")])
        self.theme_cb.set(self.t(self.theme))
        self.theme_cb.pack(side="left", padx=(4, 0))
        self.theme_cb.bind("<<ComboboxSelected>>", self.on_theme)

        # მთავარი ნაწილი / main body
        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True)

        sidebar = ttk.Frame(body, padding=8)
        sidebar.pack(side="left", fill="y")
        ttk.Label(sidebar, text=self.t("tools"),
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))

        self.container = ttk.Frame(body)
        self.container.pack(side="left", fill="both", expand=True)

        # ლოგი
        logframe = ttk.LabelFrame(self.container, text=self.t("log"), padding=4)
        logframe.pack(side="bottom", fill="x")
        logbar = ttk.Frame(logframe)
        logbar.pack(fill="x", pady=(0, 2))
        ttk.Button(logbar, text=self.t("log_save"), command=self.save_log).pack(side="right")
        ttk.Button(logbar, text=self.t("log_clear"), command=self.clear_log).pack(
            side="right", padx=(0, 4))
        self.logbox = tk.Text(logframe, height=7, wrap="word",
                              font=("Consolas", 9), state="disabled",
                              bg=p["log_bg"], fg=p["log_fg"],
                              insertbackground=p["fg"], relief="flat",
                              borderwidth=0)
        self.logbox.pack(fill="x")
        self._restore_log()

        # ინსტრუმენტების ღილაკები (frame-ები lazy-ად იქმნება show()-ში)
        self.frames = [None] * len(self.tool_specs)
        for idx, spec in enumerate(self.tool_specs):
            ttk.Button(sidebar, text=spec["name_" + self.lang], width=22,
                       command=lambda i=idx: self.show(i)).pack(
                anchor="w", pady=2)

        if self.current_tool >= len(self.tool_specs):
            self.current_tool = 0
        self.show(self.current_tool)

    def show(self, idx):
        self.current_tool = idx
        for f in self.frames:
            if f is not None:
                f.pack_forget()
        if self.frames[idx] is None:
            self.frames[idx] = self._instantiate_tool(idx)
        self.frames[idx].pack(side="top", fill="both", expand=True)

    # --- გადამრთველები ---
    def on_lang(self, _evt=None):
        for code, name in LANGS.items():
            if name == self.lang_cb.get():
                self.lang = code
        self.save_settings()
        self.rebuild_ui()

    def on_theme(self, _evt=None):
        val = self.theme_cb.get()
        self.theme = "dark" if val == self.t("dark") else "light"
        self.save_settings()
        self.rebuild_ui()

    # --- ლოგი ---
    def log(self, msg):
        self.log_lines.append(msg)
        self.logbox.configure(state="normal")
        self.logbox.insert("end", msg + "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def _restore_log(self):
        if not self.log_lines:
            return
        self.logbox.configure(state="normal")
        self.logbox.insert("end", "\n".join(self.log_lines) + "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def clear_log(self):
        self.log_lines = []
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.configure(state="disabled")

    def save_log(self):
        if not self.log_lines:
            messagebox.showinfo("GIS_BOX", self.t("log_empty"))
            return
        from datetime import datetime
        default = "gis_box_log_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt"
        path = filedialog.asksaveasfilename(
            title=self.t("log_title"), defaultextension=".txt",
            initialfile=default,
            filetypes=[("Text", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.log_lines) + "\n")
        except OSError as e:
            messagebox.showerror("GIS_BOX", str(e))
            return
        self.log(f"{self.t('log_saved')} {path}")


def _enable_dpi_awareness():
    """ეკრანის grab-ის სწორი გასწორებისთვის (კოორდ. ამომღები, Windows).

    გამოიძახება Tk ფანჯრის შექმნამდე. თუ coordextract არ არის ხელმისაწვდომი,
    უბრალოდ ვტოვებთ — GIS_BOX მაინც იმუშავებს."""
    if sys.platform != "win32":
        return
    try:
        from tools.coordextract.capture import enable_dpi_awareness
        enable_dpi_awareness()
    except Exception:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


if __name__ == "__main__":
    # ფონური (headless) გაშვება — GDB → PostGIS განრიგისთვის (Task Scheduler),
    # GUI-ს გარეშე; GIS_BOX-ის დახურვის შემდეგაც მუშაობს.
    if "--gdb2pg-run" in sys.argv:
        from tools.gdb2postgis_cli import run_headless
        sys.exit(run_headless())
    _enable_dpi_awareness()
    GisBoxApp().mainloop()
