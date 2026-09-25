# -*- coding: utf-8 -*-
"""მარტივი tooltip (hover-მინიშნება) tkinter widget-ებისთვის — დამოკიდებულების გარეშე.

გამოყენება:  Tooltip(widget, "ტექსტი")  ან  add_tip(widget, "ტექსტი").
ტექსტი ჩნდება მაუსის შეყოვნებაზე; ცარიელ ტექსტზე — არაფერი.
"""

import tkinter as tk
from tools.platform_utils import UI_FONT


class Tooltip:
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self):
        if self._tip is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 18
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:
            return
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)          # ჩარჩოს გარეშე
        tw.wm_geometry(f"+{x}+{y}")
        try:
            tw.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(tw, text=self.text, justify="left", background="#ffffe0",
                 foreground="#1a1a1a", relief="solid", borderwidth=1,
                 font=(UI_FONT, 9), wraplength=380, padx=6, pady=3).pack()

    def _hide(self, _e=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


def add_tip(widget, text):
    """ტოლტიპის მიმაგრება; აბრუნებს widget-ს (ჯაჭვისთვის)."""
    if text:
        Tooltip(widget, text)
    return widget
