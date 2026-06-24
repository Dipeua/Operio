"""
Operio — Répertoire des opérateurs
-----------------------------------
Petite application de bureau pour gérer une liste d'opérateurs
(nom + numéro de téléphone), affichée en ordre alphabétique,
avec export du tableau en PDF.

Dépendances : reportlab (PDF). tkinter est inclus avec Python.
Lancer :  python operio.py
"""

import json
import os
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)

# --------------------------------------------------------------------------- #
#  Constantes & palette de couleurs
# --------------------------------------------------------------------------- #
APP_NAME = "Operio"
APP_SUBTITLE = "Répertoire des opérateurs"
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "operateurs.json")

# Palette (thème clair & moderne)
BG        = "#f1f5f9"   # fond principal (slate 100)
CARD      = "#ffffff"   # cartes (blanc)
CARD_2    = "#f8fafc"   # fond des champs de saisie
BORDER    = "#e2e8f0"   # bordures douces
ACCENT    = "#2563eb"   # bleu accent (blue 600)
ACCENT_DK = "#1d4ed8"   # bleu accent foncé
TEXT      = "#1e293b"   # texte principal (slate 800)
MUTED     = "#64748b"   # texte secondaire (slate 500)
DANGER    = "#ef4444"
DANGER_DK = "#dc2626"
SUCCESS   = "#16a34a"
SUCCESS_DK = "#15803d"
ROW_ALT   = "#f8fafc"   # ligne alternée très claire
HEAD_BG   = "#eef2f7"   # en-tête de tableau

# Couleurs des FAI (Mobile Money)
MTN_COLOR    = "#d97706"   # ambre (MTN)
ORANGE_COLOR = "#ea580c"   # orange (Orange)


# --------------------------------------------------------------------------- #
#  Détection du FAI (Mobile Money) à partir du préfixe
# --------------------------------------------------------------------------- #
def tel_digits(tel):
    """Réduit un numéro à ses seuls chiffres (sans +237) pour comparer deux numéros.

    Ainsi « 697 89 04 66 », « 697890466 » et « +237 697 89 04 66 »
    sont reconnus comme identiques.
    """
    digits = re.sub(r"\D", "", tel)
    if digits.startswith("237") and len(digits) > 9:
        digits = digits[3:]
    return digits


def detecter_fai(tel):
    """Retourne 'MTN Money', 'Orange Money' ou '—' selon le préfixe camerounais.

    Règle (2026) : 650–654 et 670–689 → MTN · 640, 655–659 et 690–699 → Orange.
    L'indicatif pays +237 éventuel est ignoré.
    """
    digits = re.sub(r"\D", "", tel)
    if digits.startswith("237"):
        digits = digits[3:]
    if len(digits) < 3:
        return "—"
    n = int(digits[:3])
    if 650 <= n <= 654 or 670 <= n <= 689:
        return "MTN Money"
    if n == 640 or 655 <= n <= 659 or 690 <= n <= 699:
        return "Orange Money"
    return "—"


# --------------------------------------------------------------------------- #
#  Application
# --------------------------------------------------------------------------- #
class OperioApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — {APP_SUBTITLE}")
        self.geometry("820x640")
        self.minsize(720, 560)
        self.configure(bg=BG)

        self.operateurs = []          # liste de dict {"nom":..., "tel":...}
        self._build_style()
        self._build_ui()
        self._load()
        self._refresh_table()

        # Raccourcis
        self.bind("<Return>", lambda e: self._add())
        self.bind("<Control-s>", lambda e: self._export_pdf())

    # ----------------------------- Style ---------------------------------- #
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=BG, foreground=TEXT,
                        fieldbackground=CARD, font=("Segoe UI", 10))

        # Entrées
        style.configure("Operio.TEntry",
                        fieldbackground=CARD_2, foreground=TEXT,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        insertcolor=ACCENT, borderwidth=1, padding=9)
        style.map("Operio.TEntry",
                  bordercolor=[("focus", ACCENT)],
                  lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)],
                  fieldbackground=[("focus", "#ffffff")])

        # Tableau
        style.configure("Operio.Treeview",
                        background=CARD, fieldbackground=CARD,
                        foreground=TEXT, rowheight=36,
                        borderwidth=0, font=("Segoe UI", 10))
        style.configure("Operio.Treeview.Heading",
                        background=HEAD_BG, foreground=MUTED,
                        font=("Segoe UI Semibold", 10), relief="flat",
                        padding=10)
        style.map("Operio.Treeview.Heading",
                  background=[("active", BORDER)])
        style.map("Operio.Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])

        # Scrollbar
        style.configure("Operio.Vertical.TScrollbar",
                        background=BORDER, troughcolor=BG,
                        bordercolor=BG, arrowcolor=MUTED, relief="flat")

    def _btn(self, parent, text, command, bg, fg="#ffffff", hover=None):
        """Crée un bouton 'plat' coloré (tk.Button stylé)."""
        hover = hover or bg
        b = tk.Button(parent, text=text, command=command,
                      bg=bg, fg=fg, activebackground=hover,
                      activeforeground=fg, relief="flat", bd=0,
                      font=("Segoe UI Semibold", 10), cursor="hand2",
                      padx=16, pady=9)
        b.bind("<Enter>", lambda e: b.config(bg=hover))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    # ------------------------------ UI ------------------------------------ #
    def _build_ui(self):
        # ---- En-tête ----
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=24, pady=(22, 8))

        tk.Label(header, text="📇  " + APP_NAME, bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 22)).pack(anchor="w")
        tk.Label(header, text=APP_SUBTITLE, bg=BG, fg=MUTED,
                 font=("Segoe UI", 11)).pack(anchor="w")

        # ---- Carte formulaire ----
        form = tk.Frame(self, bg=CARD, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=BORDER)
        form.pack(fill="x", padx=24, pady=12)
        inner = tk.Frame(form, bg=CARD)
        inner.pack(fill="x", padx=18, pady=18)

        tk.Label(inner, text="Nom de l'opérateur", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=(0, 12))
        tk.Label(inner, text="Numéro de téléphone", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w")

        self.nom_var = tk.StringVar()
        self.tel_var = tk.StringVar()

        self.nom_entry = ttk.Entry(inner, textvariable=self.nom_var,
                                   style="Operio.TEntry", width=30)
        self.nom_entry.grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(4, 0))
        self.tel_entry = ttk.Entry(inner, textvariable=self.tel_var,
                                   style="Operio.TEntry", width=24)
        self.tel_entry.grid(row=1, column=1, sticky="ew", pady=(4, 0))

        add_btn = self._btn(inner, "＋  Ajouter", self._add, ACCENT, hover=ACCENT_DK)
        add_btn.grid(row=1, column=2, padx=(12, 0), pady=(4, 0))

        inner.columnconfigure(0, weight=2)
        inner.columnconfigure(1, weight=1)

        self.nom_entry.focus_set()

        # ---- Barre d'actions ----
        actions = tk.Frame(self, bg=BG)
        actions.pack(fill="x", padx=24, pady=(4, 0))

        self.count_lbl = tk.Label(actions, text="", bg=BG, fg=MUTED,
                                  font=("Segoe UI", 10))
        self.count_lbl.pack(side="left")

        self._btn(actions, "⬇  Exporter en PDF", self._export_pdf,
                  SUCCESS, hover=SUCCESS_DK).pack(side="right")
        self._btn(actions, "🗑  Supprimer la sélection", self._delete_selected,
                  DANGER, hover=DANGER_DK).pack(side="right", padx=(0, 10))
        self._btn(actions, "✏  Modifier", self._edit_selected,
                  "#0891b2", hover="#0e7490").pack(side="right", padx=(0, 10))

        # ---- Tableau ----
        table_wrap = tk.Frame(self, bg=CARD, highlightthickness=1,
                              highlightbackground=BORDER, highlightcolor=BORDER)
        table_wrap.pack(fill="both", expand=True, padx=24, pady=14)

        cols = ("nom", "tel", "fai")
        self.tree = ttk.Treeview(table_wrap, columns=cols, show="headings",
                                 style="Operio.Treeview", selectmode="extended")
        self.tree.heading("nom", text="Nom de l'opérateur")
        self.tree.heading("tel", text="Téléphone")
        self.tree.heading("fai", text="FAI")
        self.tree.column("nom", anchor="w", width=330)
        self.tree.column("tel", anchor="w", width=170)
        self.tree.column("fai", anchor="w", width=150)

        self.tree.tag_configure("odd", background=CARD)
        self.tree.tag_configure("even", background=ROW_ALT)
        self.tree.tag_configure("mtn", foreground=MTN_COLOR)
        self.tree.tag_configure("orange", foreground=ORANGE_COLOR)
        self.tree.tag_configure("dup", background="#fee2e2")  # doublon de numéro

        vsb = ttk.Scrollbar(table_wrap, orient="vertical",
                            command=self.tree.yview,
                            style="Operio.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        vsb.pack(side="right", fill="y", pady=6, padx=(0, 6))

        self.tree.bind("<Delete>", lambda e: self._delete_selected())
        self.tree.bind("<Double-1>", lambda e: self._edit_selected())

        # ---- Pied de page ----
        self.status = tk.Label(self, text="Prêt.", bg=BG, fg=MUTED,
                               anchor="w", font=("Segoe UI", 9))
        self.status.pack(fill="x", padx=24, pady=(0, 12))

    # --------------------------- Logique ---------------------------------- #
    def _set_status(self, msg, color=MUTED):
        self.status.config(text=msg, fg=color)

    def _add(self):
        nom = self.nom_var.get().strip()
        tel = self.tel_var.get().strip()

        if not nom:
            messagebox.showwarning("Champ manquant", "Veuillez entrer un nom d'opérateur.")
            self.nom_entry.focus_set()
            return
        if not tel:
            messagebox.showwarning("Champ manquant", "Veuillez entrer un numéro de téléphone.")
            self.tel_entry.focus_set()
            return

        # Validation légère du téléphone (chiffres, espaces, + ( ) - . )
        if not re.fullmatch(r"[0-9 +().\-]{4,}", tel):
            if not messagebox.askyesno(
                "Numéro inhabituel",
                f"« {tel} » ne ressemble pas à un numéro de téléphone.\n\nL'ajouter quand même ?"):
                return

        # Doublon de nom ?
        if any(o["nom"].lower() == nom.lower() for o in self.operateurs):
            if not messagebox.askyesno(
                "Doublon",
                f"Un opérateur nommé « {nom} » existe déjà.\n\nL'ajouter quand même ?"):
                return

        # Doublon de numéro ?
        proprio = next((o for o in self.operateurs
                        if tel_digits(o["tel"]) == tel_digits(tel)), None)
        if proprio is not None:
            if not messagebox.askyesno(
                "Numéro déjà présent",
                f"Le numéro « {tel} » est déjà attribué à « {proprio['nom']} ».\n\n"
                "L'ajouter quand même ?"):
                return

        self.operateurs.append({"nom": nom, "tel": tel})
        self._save()
        self._refresh_table()
        self._set_status(f"« {nom} » ajouté.", SUCCESS)

        # Reset du formulaire
        self.nom_var.set("")
        self.tel_var.set("")
        self.nom_entry.focus_set()

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            self._set_status("Aucune ligne sélectionnée.", DANGER)
            return
        noms = [self.tree.item(i, "values")[0] for i in sel]
        if not messagebox.askyesno(
            "Confirmer la suppression",
            f"Supprimer {len(noms)} opérateur(s) ?\n\n" + "\n".join(f"• {n}" for n in noms)):
            return
        noms_set = {n for n in noms}
        # On supprime par (nom, tel) pour viser exactement les lignes sélectionnées
        cibles = {(self.tree.item(i, "values")[0], self.tree.item(i, "values")[1]) for i in sel}
        self.operateurs = [o for o in self.operateurs
                           if (o["nom"], o["tel"]) not in cibles]
        self._save()
        self._refresh_table()
        self._set_status(f"{len(cibles)} opérateur(s) supprimé(s).", DANGER)

    def _edit_selected(self):
        sel = self.tree.selection()
        if not sel:
            self._set_status("Sélectionnez une ligne à modifier.", DANGER)
            return
        if len(sel) > 1:
            self._set_status("Sélectionnez une seule ligne à modifier.", DANGER)
            return
        vals = self.tree.item(sel[0], "values")
        old_nom, old_tel = vals[0], vals[1]
        cible = next((o for o in self.operateurs
                      if o["nom"] == old_nom and o["tel"] == old_tel), None)
        if cible is None:
            self._set_status("Opérateur introuvable.", DANGER)
            return
        self._open_edit_dialog(cible)

    def _open_edit_dialog(self, op):
        """Fenêtre modale pour modifier le nom et le numéro d'un opérateur."""
        dlg = tk.Toplevel(self)
        dlg.title("Modifier l'opérateur")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        # Centrage par rapport à la fenêtre principale
        self.update_idletasks()
        w, h = 420, 260
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")

        card = tk.Frame(dlg, bg=CARD, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=BORDER)
        card.pack(fill="both", expand=True, padx=16, pady=16)
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(inner, text="✏  Modifier l'opérateur", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 13)).grid(
                     row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        tk.Label(inner, text="Nom de l'opérateur", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w")
        nom_var = tk.StringVar(value=op["nom"])
        nom_entry = ttk.Entry(inner, textvariable=nom_var,
                              style="Operio.TEntry", width=40)
        nom_entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        tk.Label(inner, text="Numéro de téléphone", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w")
        tel_var = tk.StringVar(value=op["tel"])
        tel_entry = ttk.Entry(inner, textvariable=tel_var,
                              style="Operio.TEntry", width=40)
        tel_entry.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 16))

        inner.columnconfigure(0, weight=1)

        def enregistrer():
            nom = nom_var.get().strip()
            tel = tel_var.get().strip()
            if not nom:
                messagebox.showwarning("Champ manquant",
                                       "Veuillez entrer un nom d'opérateur.", parent=dlg)
                nom_entry.focus_set()
                return
            if not tel:
                messagebox.showwarning("Champ manquant",
                                       "Veuillez entrer un numéro de téléphone.", parent=dlg)
                tel_entry.focus_set()
                return
            if not re.fullmatch(r"[0-9 +().\-]{4,}", tel):
                if not messagebox.askyesno(
                        "Numéro inhabituel",
                        f"« {tel} » ne ressemble pas à un numéro de téléphone.\n\n"
                        "L'enregistrer quand même ?", parent=dlg):
                    return
            # Doublon de nom (en ignorant l'opérateur en cours d'édition)
            if any(o is not op and o["nom"].lower() == nom.lower()
                   for o in self.operateurs):
                if not messagebox.askyesno(
                        "Doublon",
                        f"Un autre opérateur nommé « {nom} » existe déjà.\n\n"
                        "Continuer quand même ?", parent=dlg):
                    return

            # Doublon de numéro (en ignorant l'opérateur en cours d'édition)
            proprio = next((o for o in self.operateurs
                            if o is not op and tel_digits(o["tel"]) == tel_digits(tel)), None)
            if proprio is not None:
                if not messagebox.askyesno(
                        "Numéro déjà présent",
                        f"Le numéro « {tel} » est déjà attribué à « {proprio['nom']} ».\n\n"
                        "Continuer quand même ?", parent=dlg):
                    return

            op["nom"] = nom
            op["tel"] = tel
            self._save()
            self._refresh_table()
            self._set_status(f"« {nom} » modifié.", SUCCESS)
            dlg.destroy()

        btns = tk.Frame(inner, bg=CARD)
        btns.grid(row=5, column=0, columnspan=2, sticky="e")
        self._btn(btns, "Annuler", dlg.destroy, "#e2e8f0",
                  fg=TEXT, hover="#cbd5e1").pack(side="right", padx=(10, 0))
        self._btn(btns, "✓  Enregistrer", enregistrer, ACCENT,
                  hover=ACCENT_DK).pack(side="right")

        nom_entry.focus_set()
        nom_entry.selection_range(0, "end")
        dlg.bind("<Return>", lambda e: enregistrer())
        dlg.bind("<Escape>", lambda e: dlg.destroy())

    def _sorted(self):
        return sorted(self.operateurs, key=lambda o: o["nom"].casefold())

    def _refresh_table(self):
        self.tree.delete(*self.tree.get_children())

        # Repérer les numéros présents plusieurs fois (comparaison sur les chiffres)
        compteur = {}
        for o in self.operateurs:
            compteur[tel_digits(o["tel"])] = compteur.get(tel_digits(o["tel"]), 0) + 1

        nb_doublons = 0
        for idx, o in enumerate(self._sorted()):
            tag = "even" if idx % 2 == 0 else "odd"
            fai = detecter_fai(o["tel"])
            color_tag = "mtn" if fai == "MTN Money" else "orange" if fai == "Orange Money" else None
            tags = [tag]
            if color_tag:
                tags.append(color_tag)
            if compteur.get(tel_digits(o["tel"]), 0) > 1:
                tags.append("dup")  # en dernier : surligne la ligne en doublon
                nb_doublons += 1
            self.tree.insert("", "end", values=(o["nom"], o["tel"], fai), tags=tuple(tags))

        n = len(self.operateurs)
        txt = f"{n} opérateur{'s' if n > 1 else ''} dans le répertoire"
        if nb_doublons:
            txt += f"  ·  ⚠ {nb_doublons} ligne(s) avec un numéro en double"
            self.count_lbl.config(fg=DANGER)
        else:
            self.count_lbl.config(fg=MUTED)
        self.count_lbl.config(text=txt)

    # ------------------------- Persistance -------------------------------- #
    def _load(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.operateurs = [
                        {"nom": str(d.get("nom", "")), "tel": str(d.get("tel", ""))}
                        for d in data if d.get("nom")
                    ]
            except (json.JSONDecodeError, OSError):
                self._set_status("Fichier de données illisible, on repart à zéro.", DANGER)

    def _save(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.operateurs, f, ensure_ascii=False, indent=2)
        except OSError as e:
            messagebox.showerror("Erreur", f"Impossible d'enregistrer les données :\n{e}")

    # --------------------------- Export PDF ------------------------------- #
    def _export_pdf(self):
        if not self.operateurs:
            messagebox.showinfo("Rien à exporter",
                                "Le répertoire est vide. Ajoutez au moins un opérateur.")
            return

        default_name = f"operateurs_{datetime.now():%Y-%m-%d}.pdf"
        path = filedialog.asksaveasfilename(
            title="Exporter le répertoire en PDF",
            defaultextension=".pdf",
            initialfile=default_name,
            filetypes=[("Fichier PDF", "*.pdf")])
        if not path:
            return

        try:
            self._write_pdf(path)
        except Exception as e:
            messagebox.showerror("Erreur d'export", f"L'export a échoué :\n{e}")
            return

        self._set_status(f"PDF exporté : {os.path.basename(path)}", SUCCESS)
        if messagebox.askyesno("Export réussi",
                               f"PDF créé :\n{path}\n\nVoulez-vous l'ouvrir ?"):
            try:
                os.startfile(path)  # Windows
            except Exception:
                pass

    def _write_pdf(self, path):
        doc = SimpleDocTemplate(
            path, pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
            title=f"{APP_NAME} — {APP_SUBTITLE}")

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "Title2", parent=styles["Title"], fontSize=20,
            textColor=colors.HexColor("#0ea5e9"), spaceAfter=2)
        sub_style = ParagraphStyle(
            "Sub", parent=styles["Normal"], fontSize=10,
            textColor=colors.HexColor("#64748b"))

        story = [
            Paragraph(f"{APP_NAME} — {APP_SUBTITLE}", title_style),
            Paragraph(f"Généré le {datetime.now():%d/%m/%Y à %H:%M} — "
                      f"{len(self.operateurs)} opérateur(s)", sub_style),
            Spacer(1, 0.6 * cm),
        ]

        data = [["#", "Nom de l'opérateur", "Téléphone", "FAI"]]
        fai_styles = []  # couleur du FAI ligne par ligne
        for i, o in enumerate(self._sorted(), start=1):
            fai = detecter_fai(o["tel"])
            data.append([str(i), o["nom"], o["tel"], fai])
            if fai == "MTN Money":
                fai_styles.append(("TEXTCOLOR", (3, i), (3, i), colors.HexColor(MTN_COLOR)))
                fai_styles.append(("FONTNAME", (3, i), (3, i), "Helvetica-Bold"))
            elif fai == "Orange Money":
                fai_styles.append(("TEXTCOLOR", (3, i), (3, i), colors.HexColor(ORANGE_COLOR)))
                fai_styles.append(("FONTNAME", (3, i), (3, i), "Helvetica-Bold"))

        table = Table(data, colWidths=[1.2 * cm, 7.6 * cm, 4.4 * cm, 3.8 * cm],
                      repeatRows=1)
        table.setStyle(TableStyle([
            # En-tête
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0ea5e9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            # Corps
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#1e293b")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#eef6fb")]),
            ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.HexColor("#0284c7")),
            ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ] + fai_styles))

        story.append(table)
        doc.build(story)


if __name__ == "__main__":
    app = OperioApp()
    app.mainloop()
