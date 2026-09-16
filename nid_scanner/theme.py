"""Quiet, high-contrast desktop styling without additional UI dependencies."""
from tkinter import ttk

PALETTE = {
    "background": "#EEF1ED", "surface": "#FAFBF8", "ink": "#243D36",
    "muted": "#6B7D74", "line": "#DAE2DA", "accent": "#286651",
    "hover": "#1D5140", "soft": "#E4EEE5", "preview": "#E8EDE7",
}


def apply_theme(root):
    c = PALETTE
    root.configure(background=c["background"])
    root.option_add("*TCombobox*Listbox.background", c["surface"])
    root.option_add("*TCombobox*Listbox.foreground", c["ink"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["soft"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["ink"])
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 10), background=c["background"], foreground=c["ink"])
    style.configure("TFrame", background=c["background"])
    style.configure("Card.TFrame", background=c["surface"])
    style.configure("TLabel", background=c["background"], foreground=c["ink"])
    style.configure("Title.TLabel", font=("Segoe UI", 26, "bold"))
    style.configure("Eyebrow.TLabel", foreground=c["accent"], font=("Segoe UI", 9, "bold"))
    style.configure("Muted.TLabel", foreground=c["muted"])
    style.configure("Card.TLabel", background=c["surface"])
    style.configure("CardTitle.TLabel", background=c["surface"], font=("Segoe UI", 12, "bold"))
    style.configure("CardMuted.TLabel", background=c["surface"], foreground=c["muted"], font=("Segoe UI", 9))
    style.configure("Badge.TLabel", background=c["soft"], foreground=c["accent"], padding=(12, 6), font=("Segoe UI", 9, "bold"))
    style.configure("Metric.TLabel", background=c["surface"], foreground=c["accent"], font=("Segoe UI", 12, "bold"))
    style.configure("TButton", background=c["surface"], foreground=c["ink"], bordercolor=c["line"],
                    lightcolor=c["surface"], darkcolor=c["surface"], borderwidth=1,
                    focusthickness=2, focuscolor=c["accent"], padding=(18, 11), font=("Segoe UI", 10, "bold"))
    style.map("TButton", background=[("disabled", c["background"]), ("active", c["soft"])],
              foreground=[("disabled", "#9BA79F")], bordercolor=[("active", "#A8BCAE")])
    style.configure("Accent.TButton", background=c["accent"], foreground="#FFFFFF", bordercolor=c["accent"],
                    lightcolor=c["accent"], darkcolor=c["accent"], focuscolor="#C6DED0")
    style.map("Accent.TButton", background=[("disabled", "#DDE5DD"), ("active", c["hover"])],
              foreground=[("disabled", "#8B9C90"), ("!disabled", "#FFFFFF")],
              bordercolor=[("disabled", "#DDE5DD"), ("active", c["hover"])])
    style.configure("Quiet.TButton", background=c["background"], borderwidth=0)
    style.configure("Treeview", background=c["surface"], fieldbackground=c["surface"], foreground=c["ink"],
                    borderwidth=0, font=("Segoe UI", 11), rowheight=round(root.winfo_fpixels("0.31i")))
    style.configure("Treeview.Heading", background=c["soft"], foreground=c["muted"], relief="flat",
                    borderwidth=0, font=("Segoe UI", 9, "bold"), padding=(12, 9))
    style.map("Treeview", background=[("selected", "#DCECDF")], foreground=[("selected", "#164532")])
    style.map("Treeview.Heading", background=[("active", c["soft"])])
    style.configure("TNotebook", background=c["background"], borderwidth=0, bordercolor=c["line"],
                    lightcolor=c["line"], darkcolor=c["line"], tabmargins=(0, 6, 0, 0))
    style.configure("TNotebook.Tab", background=c["background"], foreground=c["muted"], borderwidth=0,
                    bordercolor=c["line"], lightcolor=c["line"], darkcolor=c["line"],
                    padding=(20, 10), font=("Segoe UI", 10, "bold"))
    style.map("TNotebook.Tab", background=[("selected", c["surface"]), ("active", c["soft"])],
              foreground=[("selected", c["accent"])])
    style.configure("TCombobox", fieldbackground=c["surface"], background=c["soft"], foreground=c["ink"],
                    arrowcolor=c["accent"], bordercolor=c["line"], lightcolor=c["line"], darkcolor=c["line"],
                    padding=7, font=("Segoe UI", 10))
    style.map("TCombobox", fieldbackground=[("readonly", c["surface"])], selectbackground=[("readonly", c["surface"])],
              selectforeground=[("readonly", c["ink"])])
    style.configure("Horizontal.TProgressbar", background=c["accent"], troughcolor=c["soft"],
                    borderwidth=0, lightcolor=c["accent"], darkcolor=c["accent"], thickness=3)
    style.configure("TScrollbar", background="#D0DBD1", troughcolor=c["surface"], borderwidth=0,
                    arrowcolor=c["muted"], lightcolor="#D0DBD1", darkcolor="#D0DBD1", arrowsize=12)
    style.map("TScrollbar", background=[("active", "#AEBFB1")])
    style.configure("TPanedwindow", background=c["background"])
    style.configure("Sash", sashthickness=10, background=c["background"])
    return c
