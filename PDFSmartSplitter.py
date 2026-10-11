"""
PDF Smart Splitter - scegli tu gli intervalli, vedi il peso in anteprima, rinomina le
parti e salva tutto in un database (storico).

Requisiti:  pip install pypdf pymupdf ttkbootstrap
Uso:        python PDFSmartSplitter.py

Copyright (C) 2026 Giorgio Calvo
Questo programma e software libero: puoi ridistribuirlo e/o modificarlo secondo i termini
della GNU Affero General Public License come pubblicata dalla Free Software Foundation,
versione 3 della licenza o (a tua scelta) una versione successiva. Viene distribuito nella
speranza che sia utile, ma SENZA ALCUNA GARANZIA. Vedi il file LICENSE.
"""
import bisect
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk

from pypdf import PdfReader, PdfWriter

try:
    import ttkbootstrap as ttkb
except ImportError:
    ttkb = None

TEMA_PREDEFINITO = "flatly"
TEMI_CHIARI = [
    "flatly", "cosmo", "litera", "journal", "minty", "pulse", "sandstone",
    "united", "yeti", "lumen", "morph", "simplex", "cerculean",
]
TEMI_SCURI = ["darkly", "superhero", "solar", "cyborg", "vapor"]
TEMI = TEMI_CHIARI + TEMI_SCURI
_FILE_TEMA = "dividi_pdf_tema.txt"
_FILE_IMP = "dividi_pdf_impostazioni.json"


def leggi_impostazioni():
    for cartella in (_QUI, os.path.expanduser("~")):
        try:
            with open(os.path.join(cartella, _FILE_IMP), encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                return d
        except (OSError, ValueError):
            pass
    for cartella in (_QUI, os.path.expanduser("~")):
        try:
            with open(os.path.join(cartella, _FILE_TEMA), encoding="utf-8") as f:
                return {"tema": f.read().strip()}
        except OSError:
            pass
    return {}


def salva_impostazioni(d):
    for cartella in (_QUI, os.path.expanduser("~")):
        try:
            with open(os.path.join(cartella, _FILE_IMP), "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2)
            return
        except OSError:
            continue


def leggi_tema():
    nome = leggi_impostazioni().get("tema")
    return nome if nome in TEMI else TEMA_PREDEFINITO


def salva_tema(nome):
    d = leggi_impostazioni()
    d["tema"] = nome
    salva_impostazioni(d)


_CHIARA = {
    "testo": "black", "tela": "#dcdcdc", "pagina": "#f4f4f4", "bordo": "#b0b0b0",
    "didascalia": "#444444", "msg": "#555555", "fuori": "#666666", "zebra": "#f2f5f9",
    "ok": "#1a7f37", "over": "#c62828",
    "zona_bordo": "#8aa4c8", "zona_sfondo": "#f3f7fd", "zona_testo": "#3b4f66",
    "zona_ok_bordo": "#1a7f37", "zona_ok_sfondo": "#dff3e4",
    "stati": {
        "ok": ("#1a7f37", "#dff3e4"),
        "over": ("#c62828", "#fbe0e0"),
        "nd": ("#455a64", "#e3e9ec"),
    },
}
_SCURA = {
    "testo": "#e8e8e8", "tela": "#26292d", "pagina": "#3b4046", "bordo": "#5d656d",
    "didascalia": "#c3c9ce", "msg": "#b4bbc1", "fuori": "#a0a8af", "zebra": "#2e3338",
    "ok": "#57d38c", "over": "#ff8a80",
    "zona_bordo": "#5f7899", "zona_sfondo": "#232b36", "zona_testo": "#d5deea",
    "zona_ok_bordo": "#57d38c", "zona_ok_sfondo": "#1f3a2c",
    "stati": {
        "ok": ("#57d38c", "#1f3a2c"),
        "over": ("#ff8a80", "#4a2528"),
        "nd": ("#9fb0ba", "#2b373e"),
    },
}


def e_scuro():
    try:
        return bool(ttkb) and ttkb.Style().theme.type == "dark"
    except Exception:
        return False


def tavolozza():
    return _SCURA if e_scuro() else _CHIARA


_ALBERI = []


def colora_albero(tv):
    try:
        tv.tag_configure("zebra", background=tavolozza()["zebra"])
    except tk.TclError:
        pass


def Albero(master, **kw):
    tv = ttk.Treeview(master, **kw)
    _ALBERI.append(tv)
    colora_albero(tv)
    return tv


def ricolora_alberi():
    vivi = []
    for tv in _ALBERI:
        try:
            if tv.winfo_exists():
                colora_albero(tv)
                vivi.append(tv)
        except tk.TclError:
            pass
    _ALBERI[:] = vivi


class Tooltip:
    def __init__(self, widget, testo, ritardo=550):
        self.widget, self.testo, self.ritardo = widget, testo, ritardo
        self._id, self._win = None, None
        widget.bind("<Enter>", self._pianifica, add="+")
        widget.bind("<Leave>", self._nascondi, add="+")
        widget.bind("<ButtonPress>", self._nascondi, add="+")

    def _pianifica(self, ev=None):
        self._nascondi()
        try:
            self._id = self.widget.after(self.ritardo, self._mostra)
        except tk.TclError:
            self._id = None

    def _mostra(self):
        self._id = None
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            self._win = tk.Toplevel(self.widget)
            self._win.wm_overrideredirect(True)
            self._win.wm_geometry(f"+{x}+{y}")
            tk.Label(
                self._win, text=self.testo, justify="left", background="#ffffe0",
                foreground="#222222", relief="solid", borderwidth=1, padx=6, pady=3,
                wraplength=320,
            ).pack()
        except tk.TclError:
            self._win = None

    def _nascondi(self, ev=None):
        if self._id is not None:
            try:
                self.widget.after_cancel(self._id)
            except tk.TclError:
                pass
            self._id = None
        if self._win is not None:
            try:
                self._win.destroy()
            except tk.TclError:
                pass
            self._win = None


_TOOLTIPS = {
    "Sfoglia...": "Scegli un file o una cartella dal computer",
    "Anteprima peso": "Calcola il peso di ogni parte senza creare file",
    "Crea i file": "Crea i PDF delle parti: li salva su disco e nello storico",
    "Storico": "Mostra le divisioni fatte in precedenza",
    "Modifica / Unisci PDF": "Riordina, elimina o unisci le pagine di uno o piu PDF",
    "Dividi per peso...": "Propone da solo la divisione sotto il peso massimo (anche per pratiche intere)",
    "Riconosci inizi": "Trova le pagine dove inizia ogni pratica (confronto visivo con la pagina modello)",
    "Proponi divisione": "Calcola le parti piu grandi possibile sotto il peso massimo",
    "Ricalcola dagli intervalli": "Ricalcola i pesi dagli intervalli scritti a mano",
    "Annulla": "Interrompe il calcolo in corso",
    "Vedi nell'anteprima": "Mostra le parti nell'anteprima della finestra principale: puoi scorrere tutte le pagine con i confini e i pesi",
    "Apri PDF...": "Apre un PDF nell'editor (sostituisce quello attuale)",
    "Aggiungi PDF (unisci)...": "Aggiunge un altro PDF in coda alle pagine attuali",
    "Svuota tutto": "Toglie tutte le pagine dall'editor",
    "Apri da storico...": "Riapre nell'editor un PDF salvato nello storico",
    "Elimina selezionate": "Elimina le pagine selezionate (anche con il tasto Canc)",
    "Inverti ordine": "Inverte l'ordine di tutte le pagine",
    "Riordina (il resto resta)": "Mette in ordine le pagine scritte; le altre restano dove sono",
    "Tieni solo queste": "Tiene solo le pagine scritte, nell'ordine indicato",
    "Salva nuovo PDF...": "Salva le pagine attuali in un nuovo PDF",
    "Apri PDF": "Apre il file selezionato",
    "Apri cartella": "Apre la cartella che contiene il file",
    "Rinomina file...": "Cambia il nome del file selezionato",
    "Ricarica questi intervalli": "Rimette nella finestra principale gli intervalli di questa divisione",
    "Elimina dallo storico": "Toglie la divisione dallo storico (i file su disco restano)",
    "Mostra Tutti": "Toglie tutti i filtri",
    "Vai": "Scorre l'anteprima fino alla pagina indicata",
    "Chiudi": "Chiude questa finestra",
    "Apri (sostituisce)": "Apre i file scelti al posto di quelli nell'editor",
    "Aggiungi (unisce)": "Aggiunge i file scelti in coda alle pagine dell'editor",
}

_AZIONI_PRINCIPALI = ("Anteprima peso", "Proponi divisione", "Riconosci inizi")

_ICONE = {
    "Sfoglia...": "▤", "Anteprima peso": "◐", "Crea i file": "✔",
    "Storico": "↻", "Modifica / Unisci PDF": "✎", "Dividi per peso...": "÷",
    "Riconosci inizi": "◎", "Apri PDF...": "↗",
    "Aggiungi PDF (unisci)...": "+", "Apri da storico...": "↻",
    "Elimina selezionate": "✖", "Inverti ordine": "⇅",
    "Riordina (il resto resta)": "⇄", "Tieni solo queste": "✔",
    "Salva nuovo PDF...": "⇩", "Chiudi": "✕", "Apri PDF": "↗",
    "Apri cartella": "▤", "Rinomina file...": "✎",
    "Ricarica questi intervalli": "↻", "Elimina dallo storico": "✖",
    "Svuota tutto": "✖", "Vai": "→", "Mostra Tutti": "↺",
    "Proponi divisione": "▶", "Ricalcola dagli intervalli": "↻", "Annulla": "✕",
    "Vedi nell'anteprima": "◐", "Scrivimi": "✉", "Copia email": "⧉", "Tieni solo queste": "✔",
}


_BOTTONI = []


def _stile_btn(text):
    """Gerarchia visiva: crea = verde, azione principale = piena, azioni normali = col bordo
    (tema chiaro) o piene (tema scuro, dove il bordo si legge male), chiudi/annulla = grigi,
    elimina = rosso."""
    scuro = e_scuro()
    if "Elimina" in text:
        return "danger" if scuro else "danger-outline"
    if text.startswith(("Crea i file", "Salva nuovo", "Salva e usa")):
        return "success"
    if text in ("Chiudi", "Annulla", "Vai", "Svuota tutto", "Mostra Tutti"):
        return "secondary"
    if text in _AZIONI_PRINCIPALI:
        return "info" if scuro else "primary"
    return "primary" if scuro else "primary-outline"


def ricolora_bottoni():
    vivi = []
    for w, text in _BOTTONI:
        try:
            if w.winfo_exists():
                w.configure(bootstyle=_stile_btn(text))
                vivi.append((w, text))
        except tk.TclError:
            pass
    _BOTTONI[:] = vivi


def Btn(master, text="", command=None, width=None, height=1, **kw):
    tip = kw.pop("tip", None) or _TOOLTIPS.get(text)
    icona = _ICONE.get(text)
    visibile = f"{icona}  {text}" if icona else text
    if width and icona:
        width += 3
    if width:
        kw["width"] = width
    if ttkb is None:
        w = tk.Button(master, text=visibile, command=command, height=height, **kw)
    else:
        w = ttkb.Button(
            master, text=visibile, command=command, bootstyle=_stile_btn(text),
            padding=(12, 5 if height <= 1 else 9), **kw
        )
        _BOTTONI.append((w, text))
    if tip:
        Tooltip(w, tip)
    return w


def Chk(master, text="", variable=None, command=None, **kw):
    if ttkb is None:
        return ttk.Checkbutton(master, text=text, variable=variable, command=command, **kw)
    return ttkb.Checkbutton(
        master, text=text, variable=variable, command=command, bootstyle="round-toggle", **kw
    )

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

if getattr(sys, "frozen", False):
    _QUI = os.path.dirname(sys.executable)
else:
    _QUI = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(_QUI, "dividi_pdf.db")


def parse_ranges(testo, n_pagine):
    intervalli = []
    for pezzo in re.split(r"[,;\n]+", testo):
        pezzo = pezzo.strip()
        if not pezzo:
            continue
        m = re.fullmatch(r"(\d+)\s*(?:-\s*(\d+))?", pezzo)
        if not m:
            raise ValueError(f"Intervallo non valido: '{pezzo}'")
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if a < 1 or b < a or b > n_pagine:
            raise ValueError(
                f"Intervallo {a}-{b} non valido (il PDF ha {n_pagine} pagine)"
            )
        intervalli.append((a, b))
    if not intervalli:
        raise ValueError("Inserisci almeno un intervallo, per esempio: 1-100")
    return intervalli


def pagine_non_incluse(intervalli, n_pagine):
    coperte = set()
    for a, b in intervalli:
        coperte.update(range(a, b + 1))
    mancanti = [p for p in range(1, n_pagine + 1) if p not in coperte]
    if not mancanti:
        return ""
    gruppi, inizio, prec = [], mancanti[0], mancanti[0]
    for p in mancanti[1:] + [None]:
        if p is None or p != prec + 1:
            gruppi.append(f"{inizio}-{prec}" if inizio != prec else str(inizio))
            inizio = p
        prec = p if p is not None else prec
    return ", ".join(gruppi)


def costruisci_parte(reader, a, b, su_pagina=None):
    w = PdfWriter()
    for p in range(a - 1, b):
        w.add_page(reader.pages[p])
        if su_pagina:
            su_pagina()
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def barra_peso(kb, max_kb, larghezza=12):
    if not max_kb:
        return ""
    r = kb / max_kb
    pieno = max(0, min(larghezza, int(round(r * larghezza))))
    return "\u2588" * pieno + "\u2591" * (larghezza - pieno) + f" {r * 100:,.0f}%"


def pulisci_nome(nome):
    nome = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", nome).strip().strip(".")
    if nome.lower().endswith(".pdf"):
        nome = nome[:-4].rstrip(". ")
    if not nome:
        raise ValueError("Il nome del file non puo essere vuoto")
    return nome + ".pdf"


APP_NOME = "PDF Smart Splitter"
APP_VERSIONE = "1.0.0"
APP_AUTORE = "Giorgio Calvo"
APP_EMAIL = "cgiorgio78@gmail.com"
APP_LICENZA = "GNU AGPL v3"
APP_LIBRERIE = (
    ("pypdf", "licenza BSD"),
    ("PyMuPDF", "licenza GNU AGPL v3"),
    ("ttkbootstrap", "licenza MIT"),
)

_FILE_DB = "dividi_pdf_db.txt"


def leggi_percorso_db():
    """Database scelto dall'utente (File > Seleziona database). Vuoto = quello predefinito.
    Si salva nella cartella dell'utente, cosi ognuno puo usare il suo anche con lo stesso exe."""
    for cartella in (os.path.expanduser("~"), _QUI):
        try:
            with open(os.path.join(cartella, _FILE_DB), encoding="utf-8") as f:
                p = f.read().strip()
            if p:
                return p
        except OSError:
            pass
    return ""


def salva_percorso_db(percorso):
    """Ricorda il database scelto ('' = torna a quello predefinito)."""
    for cartella in (os.path.expanduser("~"), _QUI):
        try:
            with open(os.path.join(cartella, _FILE_DB), "w", encoding="utf-8") as f:
                f.write(percorso or "")
            return True
        except OSError:
            continue
    return False


def apri_db(path=None):
    percorso = path or DB_PATH
    try:
        conn = sqlite3.connect(percorso, timeout=20)
    except sqlite3.Error:
        if path:
            raise
        conn = sqlite3.connect(os.path.join(os.path.expanduser("~"), "dividi_pdf.db"))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS divisioni (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            data        TEXT NOT NULL,
            pdf_origine TEXT NOT NULL,
            n_pagine    INTEGER NOT NULL,
            kb_origine  REAL,
            cartella    TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS parti (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            divisione_id INTEGER NOT NULL REFERENCES divisioni(id) ON DELETE CASCADE,
            numero       INTEGER NOT NULL,
            pag_da       INTEGER NOT NULL,
            pag_a        INTEGER NOT NULL,
            kb           REAL NOT NULL,
            nome_file    TEXT NOT NULL,
            pdf_blob     BLOB
        );
        """
    )
    colonne = {r[1] for r in conn.execute("PRAGMA table_info(parti)")}
    if "pdf_blob" not in colonne:
        conn.execute("ALTER TABLE parti ADD COLUMN pdf_blob BLOB")
    conn.commit()
    return conn


def salva_divisione(conn, pdf_origine, n_pagine, kb_origine, cartella, parti):
    cur = conn.execute(
        "INSERT INTO divisioni (data, pdf_origine, n_pagine, kb_origine, cartella) "
        "VALUES (?, ?, ?, ?, ?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), pdf_origine, n_pagine, kb_origine, cartella),
    )
    div_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO parti (divisione_id, numero, pag_da, pag_a, kb, nome_file, pdf_blob) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(div_id, p[0], p[1], p[2], p[3], p[4], p[5]) for p in parti],
    )
    conn.commit()
    return div_id


MESI = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]


def anni_disponibili(conn):
    righe = conn.execute(
        "SELECT DISTINCT strftime('%Y', data) FROM divisioni ORDER BY 1 DESC"
    ).fetchall()
    return [r[0] for r in righe if r[0]]


def elenco_storico(conn, anno=None, mese=None, testo_cerca=None):
    filtri, parametri = [], []
    if anno:
        filtri.append("strftime('%Y', d.data) = ?")
        parametri.append(f"{int(anno):04d}")
    if mese:
        filtri.append("strftime('%m', d.data) = ?")
        parametri.append(f"{int(mese):02d}")
    if testo_cerca:
        filtri.append("p.nome_file LIKE ?")
        parametri.append(f"%{testo_cerca}%")
        
    where = ("WHERE " + " AND ".join(filtri) + " ") if filtri else ""
    return conn.execute(
        "SELECT p.id, d.id, d.data, d.pdf_origine, p.numero, p.pag_da, p.pag_a, "
        "p.kb, p.nome_file, d.cartella "
        "FROM parti p JOIN divisioni d ON d.id = p.divisione_id "
        + where
        + "ORDER BY d.data DESC, d.id DESC, p.numero",
        parametri,
    ).fetchall()


def intervalli_divisione(conn, div_id):
    righe = conn.execute(
        "SELECT pag_da, pag_a FROM parti WHERE divisione_id = ? ORDER BY numero", (div_id,)
    ).fetchall()
    return ", ".join(f"{a}-{b}" if a != b else str(a) for a, b in righe)


def rinomina_parte(conn, parte_id, nuovo_nome):
    riga = conn.execute(
        "SELECT p.nome_file, d.cartella FROM parti p "
        "JOIN divisioni d ON d.id = p.divisione_id WHERE p.id = ?",
        (parte_id,),
    ).fetchone()
    if not riga:
        raise ValueError("Parte non trovata nel database")
    vecchio, cartella = riga
    nuovo = pulisci_nome(nuovo_nome)
    if nuovo == vecchio:
        return nuovo, os.path.exists(os.path.join(cartella, vecchio))
    p_vecchio = os.path.join(cartella, vecchio)
    p_nuovo = os.path.join(cartella, nuovo)
    if os.path.exists(p_nuovo):
        raise FileExistsError(f"Esiste gia un file chiamato '{nuovo}' nella cartella")
    trovato = os.path.exists(p_vecchio)
    if trovato:
        os.rename(p_vecchio, p_nuovo)
    conn.execute("UPDATE parti SET nome_file = ? WHERE id = ?", (nuovo, parte_id))
    conn.commit()
    return nuovo, trovato


def elimina_divisione(conn, div_id):
    conn.execute("DELETE FROM parti WHERE divisione_id = ?", (div_id,))
    conn.execute("DELETE FROM divisioni WHERE id = ?", (div_id,))
    conn.commit()


def apri_con_sistema(percorso):
    if sys.platform.startswith("win"):
        os.startfile(percorso)
    elif sys.platform == "darwin":
        subprocess.run(["open", percorso], check=False)
    else:
        subprocess.run(["xdg-open", percorso], check=False)


def mostra_in_cartella(percorso):
    norm_path = os.path.normpath(percorso)
    if sys.platform.startswith("win"):
        if os.path.isdir(norm_path):
            subprocess.run(f'explorer "{norm_path}"', shell=True, check=False)
        else:
            subprocess.run(f'explorer /select,"{norm_path}"', shell=True, check=False)
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", norm_path], check=False)
    else:
        if os.path.isdir(norm_path):
            subprocess.run(["xdg-open", norm_path], check=False)
        else:
            subprocess.run(["xdg-open", os.path.dirname(norm_path)], check=False)


def parse_sequenza(testo, n_pagine):
    risultato = []
    for pezzo in re.split(r"[,;\n]+", testo):
        pezzo = pezzo.strip()
        if not pezzo:
            continue
        m = re.fullmatch(r"(\d+)\s*(?:-\s*(\d+))?", pezzo)
        if not m:
            raise ValueError(f"Valore non valido: '{pezzo}'")
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if min(a, b) < 1 or max(a, b) > n_pagine:
            raise ValueError(f"'{pezzo}' fuori limite (ci sono {n_pagine} pagine)")
        passo = 1 if b >= a else -1
        risultato.extend(range(a, b + passo, passo))
    if not risultato:
        raise ValueError("Scrivi almeno una pagina, per esempio: 3,4,5")
    return risultato


def _apri_doc(percorso, blob):
    doc = fitz.open(stream=blob, filetype="pdf") if blob else fitz.open(percorso)
    if doc.needs_pass:
        doc.authenticate("")
    return doc


def dimensioni_pagine(percorso, blob, indici):
    doc = _apri_doc(percorso, blob)
    try:
        return {p: (doc[p].rect.width, doc[p].rect.height) for p in indici}
    finally:
        doc.close()


def render_pagine_png(percorso, blob, indici, larghezza):
    doc = _apri_doc(percorso, blob)
    try:
        out = {}
        for p in indici:
            page = doc[p]
            scala = larghezza / page.rect.width
            pix = page.get_pixmap(matrix=fitz.Matrix(scala, scala), alpha=False)
            out[p] = pix.tobytes("png")
        return out
    finally:
        doc.close()


class FinestraBase(tk.Toplevel):
    """Toplevel che eredita lo sfondo del tema attivo di ttkbootstrap."""
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.aggiorna_sfondo()

    def aggiorna_sfondo(self):
        if ttkb:
            colore_bg = ttkb.Style().colors.bg
            self.configure(background=colore_bg)


class EditorPDF(FinestraBase):
    def __init__(self, master, percorso_iniziale=None):
        super().__init__(master)
        self.title("Modifica / Unisci PDF")
        self.geometry("1100x640")
        self.transient(master)
        self.sorgenti = []
        self.pagine = []
        self.var_seq = tk.StringVar()
        self.var_vai_a = tk.StringVar()
        self._blobs = {}
        self._dim = {}
        self._tops, self._hs, self._tot = [], [], 0
        self._items = {}
        self._after_id = None
        self._salta_scroll = False

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(10, 0))
        Btn(top, text="Apri PDF...", command=self.apri, width=16).pack(side="left", padx=(0, 5))
        Btn(top, text="Aggiungi PDF (unisci)...", command=self.aggiungi, width=22).pack(
            side="left", padx=5
        )
        Btn(top, text="Svuota tutto", command=self.svuota, width=12).pack(side="left", padx=5)
        Btn(top, text="Apri da storico...", command=self.apri_da_storico, width=18).pack(
            side="left", padx=5
        )
        self.lbl_info = ttk.Label(self, text="Nessun PDF caricato", anchor="w")
        self.lbl_info.pack(fill="x", padx=10, pady=(4, 0))

        seq = ttk.LabelFrame(self, text="Scrivi le pagine (posizioni nella lista qui sotto)")
        seq.pack(fill="x", padx=10, pady=(8, 0))
        ttk.Label(
            seq,
            text="Es. 2,1 = scambia la 1 e la 2, il resto resta com'e   |   5-3 = inverte il blocco 3-5   |   3,4,5 = pagine da tenere",
            anchor="w",
        ).pack(fill="x", padx=5)
        r = ttk.Frame(seq)
        r.pack(fill="x", padx=5, pady=(0, 5))
        e = ttk.Entry(r, textvariable=self.var_seq)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<Return>", lambda ev: self.riordina_sequenza())
        Btn(r, text="Riordina (il resto resta)", command=self.riordina_sequenza, width=22).pack(
            side="left", padx=5
        )
        Btn(r, text="Tieni solo queste", command=self.applica_sequenza, width=16).pack(side="left")

        cont = ttk.Frame(self)
        cont.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        self.frm_prev = ttk.LabelFrame(cont, text="Anteprima (tutte le pagine)", width=self._PW + 52)
        self.frm_prev.pack(side="right", fill="y", padx=(8, 0))
        self.frm_prev.pack_propagate(False)

        frm_vai = ttk.Frame(self.frm_prev)
        frm_vai.pack(fill="x", padx=4, pady=(2, 4))
        ttk.Label(frm_vai, text="Pagina:").pack(side="left")
        e_vai = ttk.Entry(frm_vai, textvariable=self.var_vai_a, width=6)
        e_vai.pack(side="left", padx=3)
        e_vai.bind("<Return>", lambda ev: self.vai_a_pagina())
        Btn(frm_vai, text="Vai", command=self.vai_a_pagina, width=6).pack(side="left")

        frm_cv = ttk.Frame(self.frm_prev)
        frm_cv.pack(fill="both", expand=True)
        sbp = ttk.Scrollbar(frm_cv, orient="vertical")
        sbp.pack(side="right", fill="y")
        self.cv = tk.Canvas(
            frm_cv, width=self._PW + 10, bg=tavolozza()["tela"], highlightthickness=0, yscrollincrement=40
        )
        self.cv.pack(side="left", fill="both", expand=True)
        sbp.configure(command=self.cv.yview)
        self.cv.configure(yscrollcommand=lambda a, b: (sbp.set(a, b), self._pianifica_render()))
        self.cv.bind("<MouseWheel>", self._rotella)
        self.cv.bind("<Button-4>", self._rotella)
        self.cv.bind("<Button-5>", self._rotella)
        self.cv.bind("<Button-1>", self._click_anteprima)
        self.cv.bind("<Configure>", lambda ev: self._pianifica_render())
        self.tree = Albero(
            cont, columns=("pos", "file", "pag"), show="headings", selectmode="extended"
        )
        for col, testo, larg, anc in (
            ("pos", "Pos.", 60, "center"),
            ("file", "File di origine", 460, "w"),
            ("pag", "Pagina originale", 120, "center"),
        ):
            self.tree.heading(col, text=testo)
            self.tree.column(col, width=larg, anchor=anc)
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(cont, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Delete>", lambda ev: self.elimina())
        self.tree.bind("<<TreeviewSelect>>", self._mostra_anteprima)

        # barra in basso: impacchettata PRIMA (dal fondo) cosi resta sempre visibile
        barra = ttk.Frame(self)
        barra.pack(side="bottom", fill="x", padx=10, pady=(8, 10), before=cont)
        gr_ord = ttk.LabelFrame(barra, text="Ordine e pagine selezionate")
        gr_ord.pack(side="left")
        Btn(gr_ord, text="▲ Su", command=lambda: self.sposta(-1), width=9).pack(side="left", padx=(6, 3), pady=5)
        Btn(gr_ord, text="▼ Giu", command=lambda: self.sposta(1), width=9).pack(side="left", padx=3, pady=5)
        Btn(gr_ord, text="Inverti ordine", command=self.inverti, width=15).pack(side="left", padx=3, pady=5)
        Btn(gr_ord, text="Elimina selezionate", command=self.elimina, width=19).pack(
            side="left", padx=(3, 6), pady=5
        )
        Btn(barra, text="Chiudi", command=self.destroy, height=2, width=10).pack(side="right", padx=(8, 0))
        Btn(barra, text="Salva nuovo PDF...", command=self.salva, height=2, width=22).pack(side="right")

        if percorso_iniziale and os.path.isfile(percorso_iniziale):
            self._carica(percorso_iniziale, aggiungi=False)

        self.after(200, lambda: _abilita_dnd_nativo_win(self, self._drop_files))

    def applica_tema(self):
        self.aggiorna_sfondo()
        self.cv.configure(bg=tavolozza()["tela"])
        self._costruisci_anteprima()

    def _drop_files(self, files):
        for k, p in enumerate(files):
            self._carica(p, aggiungi=bool(self.pagine) or k > 0)

    def vai_a_pagina(self):
        if not self.pagine:
            messagebox.showwarning("Attenzione", "Carica prima un PDF.", parent=self)
            return
        val = self.var_vai_a.get().strip()
        if not val.isdigit():
            messagebox.showwarning("Attenzione", "Inserisci un numero di pagina valido.", parent=self)
            return
        p = int(val)
        if not (1 <= p <= len(self.pagine)):
            messagebox.showwarning(
                "Attenzione", f"Pagina non valida. Inserisci un numero tra 1 e {len(self.pagine)}.", parent=self
            )
            return
        idx = p - 1
        self.tree.selection_set(str(idx))
        self.tree.see(str(idx))
        self._salta_scroll = False
        self._mostra_anteprima()

    def _carica(self, percorso, aggiungi):
        try:
            reader = PdfReader(percorso)
            if reader.is_encrypted and not reader.decrypt(""):
                raise ValueError("Il PDF e protetto da password")
            n = len(reader.pages)
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile aprire il PDF:\n{e}", parent=self)
            return
        if not aggiungi:
            self.sorgenti, self.pagine = [], []
        self.sorgenti.append((percorso, reader))
        idx = len(self.sorgenti) - 1
        self.pagine.extend((idx, p) for p in range(n))
        self._ridisegna()

    def apri(self):
        p = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")], parent=self)
        if p:
            self._carica(p, aggiungi=False)

    def aggiungi(self):
        ps = filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")], parent=self)
        for p in ps:
            self._carica(p, aggiungi=True)

    def _carica_blob(self, percorso, dati, aggiungi):
        try:
            reader = PdfReader(io.BytesIO(dati))
            n = len(reader.pages)
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile aprire il PDF dal database:\n{e}", parent=self)
            return
        if not aggiungi:
            self.sorgenti, self.pagine = [], []
        self._blobs[percorso] = dati
        self.sorgenti.append((percorso, reader))
        idx = len(self.sorgenti) - 1
        self.pagine.extend((idx, p) for p in range(n))
        self._ridisegna()

    def apri_da_storico(self):
        conn = self.master.conn
        win = FinestraBase(self)
        win.title("Apri da storico")
        win.geometry("840x420")
        win.transient(self)

        var_cerca = tk.StringVar()
        top = ttk.Frame(win)
        top.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Label(top, text="Cerca (Nome file):").pack(side="left")
        txt = ttk.Entry(top, textvariable=var_cerca, width=30)
        txt.pack(side="left", padx=5)
        lbl = ttk.Label(top, text="")
        lbl.pack(side="right")

        tree = Albero(
            win, columns=("data", "nome", "pagine", "kb", "cartella"),
            show="headings", selectmode="extended",
        )
        for col, testo, larg in (
            ("data", "Data", 110), ("nome", "Nome file", 280), ("pagine", "Pagine", 70),
            ("kb", "KB", 65), ("cartella", "Cartella", 260),
        ):
            tree.heading(col, text=testo)
            tree.column(col, width=larg, anchor="w")
        tree.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        mappa = {}

        def ricarica(event=None):
            tree.delete(*tree.get_children())
            mappa.clear()
            righe = elenco_storico(conn, None, None, var_cerca.get().strip() or None)
            for (pid, did, data, pdf, num, a, b, kb, nome, cart) in righe:
                iid = tree.insert(
                    "", "end", tags=("zebra",) if len(tree.get_children()) % 2 else (),
                    values=(data, nome, f"{a}-{b}" if a != b else a, f"{kb:,.0f}", cart),
                )
                mappa[iid] = (pid, nome, cart)
            lbl.config(text=f"{len(righe)} file" if righe else "Nessun risultato")

        def carica(aggiungi):
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Storico", "Seleziona prima una o piu righe.", parent=win)
                return
            for k, iid in enumerate(sel):
                pid, nome, cart = mappa[iid]
                percorso = os.path.join(cart, nome)
                agg = aggiungi or k > 0
                if os.path.exists(percorso):
                    self._carica(percorso, aggiungi=agg)
                    continue
                riga = conn.execute("SELECT pdf_blob FROM parti WHERE id = ?", (pid,)).fetchone()
                if riga and riga[0]:
                    self._carica_blob(percorso, riga[0], aggiungi=agg)
                else:
                    messagebox.showinfo(
                        "File non trovato",
                        f"Il file non e su disco e non c'e un backup nel database:\n\n{percorso}",
                        parent=win,
                    )
            win.destroy()

        txt.bind("<KeyRelease>", ricarica)
        tree.bind("<Double-1>", lambda ev: carica(bool(self.pagine)))

        botti = ttk.Frame(win)
        botti.pack(pady=10)
        Btn(botti, text="Apri (sostituisce)", command=lambda: carica(False), width=20).pack(
            side="left", padx=5
        )
        Btn(botti, text="Aggiungi (unisce)", command=lambda: carica(True), width=20).pack(
            side="left", padx=5
        )
        Btn(botti, text="Chiudi", command=win.destroy, width=10).pack(side="left", padx=5)
        ricarica()
        txt.focus_set()

    def svuota(self):
        self.sorgenti, self.pagine = [], []
        self._ridisegna()

    def _ridisegna(self, seleziona=None):
        self.tree.delete(*self.tree.get_children())
        for i, (s, p) in enumerate(self.pagine):
            nome = os.path.basename(self.sorgenti[s][0])
            self.tree.insert(
                "", "end", iid=str(i), values=(i + 1, nome, p + 1),
                tags=("zebra",) if i % 2 else (),
            )
        if seleziona:
            validi = [str(i) for i in seleziona if 0 <= i < len(self.pagine)]
            if validi:
                self.tree.selection_set(validi)
                self.tree.see(validi[0])
        if self.pagine:
            self.lbl_info.config(
                text=f"{len(self.pagine)} pagine da {len(self.sorgenti)} file"
            )
        else:
            self.lbl_info.config(text="Nessun PDF caricato")
        self._costruisci_anteprima()

    _PW, _CAP, _GAP = 290, 16, 8

    def _costruisci_anteprima(self):
        cv, PW, CAP = self.cv, self._PW, self._CAP
        cv.delete("all")
        self._items, self._tops, self._hs, self._tot = {}, [], [], 0
        if fitz is None:
            cv.configure(scrollregion=(0, 0, PW + 10, 10))
            cv.create_text(
                8, 12, anchor="nw", width=PW,
                text="Anteprima non disponibile.\nInstalla:  pip install pymupdf", fill=tavolozza()["msg"],
            )
            return
        if not self.pagine:
            cv.configure(scrollregion=(0, 0, PW + 10, 10))
            cv.create_text(8, 12, anchor="nw", width=PW, text="Nessuna pagina da mostrare.", fill=tavolozza()["msg"])
            return
        da_misurare = {}
        for s_, p in self.pagine:
            percorso = self.sorgenti[s_][0]
            if (percorso, p) not in self._dim:
                da_misurare.setdefault(percorso, set()).add(p)
        for percorso, ps in da_misurare.items():
            try:
                for p, wh in dimensioni_pagine(percorso, self._blobs.get(percorso), sorted(ps)).items():
                    self._dim[(percorso, p)] = wh
            except Exception:
                for p in ps:
                    self._dim[(percorso, p)] = (595.0, 842.0)
        y = 4
        for i, (s_, p) in enumerate(self.pagine):
            percorso = self.sorgenti[s_][0]
            w, h = self._dim.get((percorso, p), (595.0, 842.0))
            hh = max(40, min(int(PW * h / max(w, 1)), PW * 4))
            self._tops.append(y)
            self._hs.append(hh)
            nome = os.path.basename(percorso)
            if len(nome) > 26:
                nome = nome[:25] + "…"
            cv.create_text(5, y, anchor="nw", text=f"{i + 1}  -  pag. {p + 1} di {nome}", fill=tavolozza()["didascalia"])
            cv.create_rectangle(
                5, y + CAP, 5 + PW, y + CAP + hh,
                fill=tavolozza()["pagina"], outline=tavolozza()["bordo"],
            )
            y += CAP + hh + self._GAP
        self._tot = y
        cv.configure(scrollregion=(0, 0, PW + 10, y))
        self._mostra_anteprima()
        self._pianifica_render()

    def _pianifica_render(self):
        if self._after_id is None:
            self._after_id = self.after(60, self._render_visibili)

    def _render_visibili(self):
        self._after_id = None
        if fitz is None or not self._tops:
            return
        try:
            cv, PW, CAP = self.cv, self._PW, self._CAP
            alto = cv.canvasy(0)
            basso = alto + max(cv.winfo_height(), 200)
            marg = 350
            a = max(0, bisect.bisect_right(self._tops, alto - marg) - 1)
            i = a
            da_fare = {}
            while i < len(self._tops) and self._tops[i] <= basso + marg:
                if i not in self._items:
                    s_, p = self.pagine[i]
                    da_fare.setdefault(self.sorgenti[s_][0], []).append((i, p))
                i += 1
            for percorso, lista in da_fare.items():
                png = render_pagine_png(
                    percorso, self._blobs.get(percorso), sorted({p for _, p in lista}), PW
                )
                for idx, p in lista:
                    img = tk.PhotoImage(data=png[p])
                    item = cv.create_image(5, self._tops[idx] + CAP, anchor="nw", image=img)
                    self._items[idx] = (item, img)
            if len(self._items) > 30:
                for idx in [k for k in self._items if k < a - 8 or k > i + 8]:
                    cv.delete(self._items[idx][0])
                    del self._items[idx]
            cv.tag_raise("sel")
        except Exception:
            pass

    def _mostra_anteprima(self, event=None):
        if fitz is None or not self._tops:
            return
        cv = self.cv
        cv.delete("sel")
        sel = [i for i in self._selezionate() if i < len(self._tops)]
        for i in sel:
            top = self._tops[i]
            cv.create_rectangle(
                2, top - 2, self._PW + 8, top + self._CAP + self._hs[i] + 2,
                outline="#1a73e8", width=3, tags="sel",
            )
        if sel and not self._salta_scroll:
            cv.yview_moveto(max(0, self._tops[sel[0]] - 4) / max(self._tot, 1))
        self._salta_scroll = False

    def _click_anteprima(self, ev):
        if not self._tops:
            return
        i = bisect.bisect_right(self._tops, self.cv.canvasy(ev.y)) - 1
        if 0 <= i < len(self._tops) and self.tree.selection() != (str(i),):
            self._salta_scroll = True
            self.tree.selection_set([str(i)])
            self.tree.see(str(i))

    def _rotella(self, ev):
        if getattr(ev, "num", None) == 4:
            d = -1
        elif getattr(ev, "num", None) == 5:
            d = 1
        else:
            d = -1 if ev.delta > 0 else 1
        self.cv.yview_scroll(d * 3, "units")

    def _selezionate(self):
        return sorted(int(i) for i in self.tree.selection())

    def elimina(self):
        sel = self._selezionate()
        if not sel:
            messagebox.showinfo("Modifica", "Seleziona prima una o piu pagine.", parent=self)
            return
        s = set(sel)
        self.pagine = [x for i, x in enumerate(self.pagine) if i not in s]
        self._ridisegna([min(sel)] if self.pagine else None)

    def sposta(self, direzione):
        sel = self._selezionate()
        if not sel:
            messagebox.showinfo("Modifica", "Seleziona prima una o piu pagine.", parent=self)
            return
        n = len(self.pagine)
        if direzione < 0:
            if sel[0] == 0:
                return
            for i in sel:
                self.pagine[i - 1], self.pagine[i] = self.pagine[i], self.pagine[i - 1]
            nuove = [i - 1 for i in sel]
        else:
            if sel[-1] == n - 1:
                return
            for i in reversed(sel):
                self.pagine[i + 1], self.pagine[i] = self.pagine[i], self.pagine[i + 1]
            nuove = [i + 1 for i in sel]
        self._ridisegna(nuove)

    def inverti(self):
        self.pagine.reverse()
        self._ridisegna()

    def riordina_sequenza(self):
        if not self.pagine:
            messagebox.showwarning("Attenzione", "Carica prima un PDF.", parent=self)
            return
        try:
            seq = parse_sequenza(self.var_seq.get(), len(self.pagine))
        except ValueError as e:
            messagebox.showerror("Errore", str(e), parent=self)
            return
        if len(set(seq)) != len(seq):
            messagebox.showerror(
                "Errore",
                "In 'Riordina' ogni pagina puo comparire una sola volta.\n"
                "(Per ripetere o scartare pagine usa 'Tieni solo queste'.)",
                parent=self,
            )
            return
        slot = sorted(seq)
        nuove = list(self.pagine)
        for posto, i in zip(slot, seq):
            nuove[posto - 1] = self.pagine[i - 1]
        self.pagine = nuove
        self._ridisegna([p - 1 for p in slot])

    def applica_sequenza(self):
        if not self.pagine:
            messagebox.showwarning("Attenzione", "Carica prima un PDF.", parent=self)
            return
        try:
            seq = parse_sequenza(self.var_seq.get(), len(self.pagine))
        except ValueError as e:
            messagebox.showerror("Errore", str(e), parent=self)
            return
        self.pagine = [self.pagine[i - 1] for i in seq]
        self._ridisegna()

    def salva(self):
        if not self.pagine:
            messagebox.showwarning("Attenzione", "Non ci sono pagine da salvare.", parent=self)
            return
        iniziale = os.path.dirname(self.sorgenti[0][0]) if self.sorgenti else ""
        base = os.path.splitext(os.path.basename(self.sorgenti[0][0]))[0] if self.sorgenti else "nuovo"
        out = filedialog.asksaveasfilename(
            parent=self, defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
            initialdir=iniziale, initialfile=f"{base}_modificato.pdf",
        )
        if not out:
            return
        if any(os.path.abspath(out) == os.path.abspath(p) for p, _ in self.sorgenti):
            messagebox.showerror(
                "Errore", "Non puoi sovrascrivere uno dei PDF sorgente: scegli un altro nome.",
                parent=self,
            )
            return
        try:
            w = PdfWriter()
            for s, p in self.pagine:
                w.add_page(self.sorgenti[s][1].pages[p])
            buf = io.BytesIO()
            w.write(buf)
            dati = buf.getvalue()
            with open(out, "wb") as f:
                f.write(dati)
        except Exception as e:
            messagebox.showerror("Errore", f"Salvataggio non riuscito:\n{e}", parent=self)
            return
        kb = len(dati) / 1024
        n = len(self.pagine)

        nota_db = ""
        try:
            origini = []
            kb_origine = 0.0
            for p, _ in self.sorgenti:
                origini.append(os.path.basename(p))
                if os.path.exists(p):
                    kb_origine += os.path.getsize(p) / 1024
            etichetta = "Modifica: " + " + ".join(origini)
            div_id = salva_divisione(
                self.master.conn, etichetta, n, kb_origine, os.path.dirname(out),
                [(1, 1, n, kb, os.path.basename(out), dati)],
            )
            nota_db = f"\n\nRegistrato nello storico (n. {div_id})."
        except Exception as e:
            nota_db = f"\n\nATTENZIONE: file salvato ma NON registrato nello storico:\n{e}"
        messagebox.showinfo(
            "Fatto", f"Salvato PDF di {n} pagine ({kb:,.0f} KB):\n{out}{nota_db}", parent=self
        )


class AnteprimaDivisione(ttk.LabelFrame):
    PW, CAP, GAP = 270, 14, 6

    def __init__(self, master):
        super().__init__(master, text="Anteprima", width=self.PW + 52)
        self.pack_propagate(False)
        self.var_vai_a = tk.StringVar()

        frm_vai = ttk.Frame(self)
        frm_vai.pack(fill="x", padx=4, pady=(2, 4))
        ttk.Label(frm_vai, text="Pagina:").pack(side="left")
        e_vai = ttk.Entry(frm_vai, textvariable=self.var_vai_a, width=6)
        e_vai.pack(side="left", padx=3)
        e_vai.bind("<Return>", lambda ev: self.vai_a_pagina())
        Btn(frm_vai, text="Vai", command=self.vai_a_pagina, width=6).pack(side="left")

        frm_cv = ttk.Frame(self)
        frm_cv.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(frm_cv, orient="vertical")
        sb.pack(side="right", fill="y")
        self.cv = tk.Canvas(
            frm_cv, width=self.PW + 10, bg=tavolozza()["tela"], highlightthickness=0, yscrollincrement=40
        )
        self.cv.pack(side="left", fill="both", expand=True)
        sb.configure(command=self.cv.yview)
        self.cv.configure(yscrollcommand=lambda a, b: (sb.set(a, b), self._pianifica()))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.cv.bind(ev, self._rotella)
        self.cv.bind("<Configure>", lambda ev: self._pianifica())
        self.percorso, self.dim, self.n = None, {}, 0
        self.parti = []
        self._sel = None
        self._pag_sel = None
        self._after = None
        self._cache = {}
        self._cop = []
        self._reset_righe()
        self._messaggio("Scegli un file PDF\nper vederne l'anteprima")

    def vai_a_pagina(self):
        if not self._r:
            messagebox.showwarning("Attenzione", "Scegli prima un file PDF.", parent=self)
            return
        val = self.var_vai_a.get().strip()
        if not val.isdigit():
            messagebox.showwarning("Attenzione", "Inserisci un numero di pagina valido.", parent=self)
            return
        p = int(val)
        if not (1 <= p <= self.n):
            messagebox.showwarning(
                "Attenzione", f"Pagina non valida. Inserisci un numero tra 1 e {self.n}.", parent=self
            )
            return
        k = self._row_pag.get(p - 1)
        if k is None:
            return
        vecchio, self._pag_sel = self._pag_sel, p - 1
        for idx in (vecchio, p - 1):
            kk = self._row_pag.get(idx) if idx is not None else None
            if kk in self._disegnate:
                for i in self._disegnate.pop(kk):
                    self.cv.delete(i)
                self._ref.pop(kk, None)
        while k > 0 and self._r[k - 1][0] in ("ban", "fuori"):
            k -= 1
        self.cv.yview_moveto(max(0, self._r[k][1] - 4) / max(self._tot, 1))
        self._pianifica()

    def applica_tema(self):
        self.cv.configure(bg=tavolozza()["tela"])
        if self.percorso:
            self._ricostruisci()
        elif getattr(self, "_ultimo_msg", None):
            self._messaggio(self._ultimo_msg)

    def _reset_righe(self):
        self._r, self._ys, self._tot = [], [], 0
        self._ban = {}
        self._row_pag = {}
        self._disegnate = {}
        self._ref = {}

    def _messaggio(self, testo):
        self._ultimo_msg = testo
        self.cv.delete("all")
        self._reset_righe()
        self.cv.configure(scrollregion=(0, 0, self.PW + 10, 10))
        self.cv.create_text(8, 12, anchor="nw", width=self.PW, text=testo, fill=tavolozza()["msg"])

    def carica(self, percorso):
        self.percorso, self.dim, self.n, self.parti, self._sel = None, {}, 0, [], None
        self._pag_sel = None
        self._cache.clear()
        self.config(text="Anteprima")
        if fitz is None:
            self._messaggio("Anteprima non disponibile.\nInstalla:  pip install pymupdf")
            return
        try:
            doc = _apri_doc(percorso, None)
            try:
                self.n = doc.page_count
                self.dim = {i: (doc[i].rect.width, doc[i].rect.height) for i in range(self.n)}
            finally:
                doc.close()
        except Exception as e:
            self.n, self.dim = 0, {}
            self._messaggio(f"Anteprima non riuscita:\n{e}")
            return
        self.percorso = percorso
        self._ricostruisci()

    def imposta_parti(self, parti):
        self.parti = list(parti)
        self._sel = None
        titolo = "Anteprima"
        if self.parti:
            titolo += f" - {len(self.parti)} parti"
            if all(p["kb"] is not None for p in self.parti):
                titolo += f" - totale {sum(p['kb'] for p in self.parti):,.0f} KB"
        self.config(text=titolo)
        if self.percorso:
            self._ricostruisci()

    def vai_a_parte(self, k):
        if k not in self._ban:
            return
        self._sel = k
        for kk in [kk for kk in self._disegnate if self._r[kk][0] == "ban"]:
            for i in self._disegnate.pop(kk):
                self.cv.delete(i)
        y = self._r[self._ban[k]][1]
        self.cv.yview_moveto(max(0, y - 4) / max(self._tot, 1))
        self._pianifica()

    def _ricostruisci(self):
        PW, CAP = self.PW, self.CAP
        self.cv.delete("all")
        self._reset_righe()
        n = self.n
        cop = [None] * (n + 2)
        inizi = {}
        for k, p in enumerate(self.parti):
            inizi.setdefault(p["a"], []).append(k)
            for pg in range(p["a"], p["b"] + 1):
                if cop[pg] is None:
                    cop[pg] = k
        self._cop = cop
        righe, ys, y = [], [], 4
        in_fuori = False
        for pg in range(1, n + 1):
            fuori = bool(self.parti) and cop[pg] is None
            if fuori and not in_fuori:
                fine = pg
                while fine + 1 <= n and cop[fine + 1] is None:
                    fine += 1
                testo = f"Pagine non incluse: {pg}" + (f"-{fine}" if fine != pg else "")
                righe.append(("fuori", y, 20, testo))
                ys.append(y)
                y += 24
            in_fuori = fuori
            for k in inizi.get(pg, []):
                self._ban[k] = len(righe)
                righe.append(("ban", y, 38, k))
                ys.append(y)
                y += 42
            w, h = self.dim.get(pg - 1, (595.0, 842.0))
            hh = max(40, min(int(PW * h / max(w, 1)), PW * 4))
            self._row_pag[pg - 1] = len(righe)
            righe.append(("pag", y, CAP + hh, pg - 1))
            ys.append(y)
            y += CAP + hh + self.GAP
        self._r, self._ys, self._tot = righe, ys, y
        self.cv.configure(scrollregion=(0, 0, PW + 10, y))
        self._pianifica()

    def _disegna_riga(self, k):
        cv, PW, CAP = self.cv, self.PW, self.CAP
        tipo, y, h, dati = self._r[k]
        ids = []
        if tipo == "fuori":
            ids.append(cv.create_text(6, y + 2, anchor="nw", text=dati, fill=tavolozza()["fuori"]))
        elif tipo == "ban":
            p = self.parti[dati]
            fg, bg = tavolozza()["stati"][p["stato"]]
            pag = f"{p['a']}-{p['b']}" if p["a"] != p["b"] else str(p["a"])
            if p["stato"] == "nd":
                riga2 = 'peso: premi "Anteprima peso"'
            elif p["stato"] == "ok":
                riga2 = f"{p['kb']:,.0f} KB  -  OK"
            else:
                riga2 = f"{p['kb']:,.0f} KB  -  SOPRA di {p['kb'] - p['max']:,.0f} KB"
            if p.get("storico") and p["stato"] != "nd":
                riga2 += "  (storico)"
            sel = dati == self._sel
            ids.append(cv.create_rectangle(
                3, y, PW + 7, y + h, fill=bg, outline="#1a73e8" if sel else fg, width=3 if sel else 1
            ))
            ids.append(cv.create_text(
                9, y + 4, anchor="nw", width=PW - 6, fill=fg,
                text=f"Parte {dati + 1}  -  pag. {pag}\n{riga2}",
            ))
        else:
            parte = self._cop[dati + 1]
            if parte is not None:
                fg = tavolozza()["stati"][self.parti[parte]["stato"]][0]
                ids.append(cv.create_rectangle(0, y, 4, y + h, fill=fg, outline=fg))
            ids.append(cv.create_text(9, y, anchor="nw", text=f"pag. {dati + 1}", fill=tavolozza()["didascalia"]))
            ids.append(cv.create_rectangle(
                7, y + CAP, 7 + PW, y + h, fill=tavolozza()["pagina"], outline=tavolozza()["bordo"]
            ))
        self._disegnate[k] = ids

    def _pianifica(self):
        if self._after is None:
            self._after = self.after(60, self._render)

    def _render(self):
        self._after = None
        if not self._r or fitz is None or not self.percorso:
            return
        try:
            cv = self.cv
            alto = cv.canvasy(0)
            basso = alto + max(cv.winfo_height(), 200)
            marg = 300
            a = max(0, bisect.bisect_right(self._ys, alto - marg) - 1)
            b = bisect.bisect_right(self._ys, basso + marg)
            nuove = []
            for k in range(a, b):
                if k not in self._disegnate:
                    self._disegna_riga(k)
                    if self._r[k][0] == "pag":
                        nuove.append(k)
            mancano = sorted({self._r[k][3] for k in nuove if self._r[k][3] not in self._cache})
            if mancano:
                png = render_pagine_png(self.percorso, None, mancano, self.PW)
                for idx in mancano:
                    self._cache[idx] = tk.PhotoImage(data=png[idx])
                while len(self._cache) > 80:
                    self._cache.pop(next(iter(self._cache)))
            for k in nuove:
                tipo, y, h, idx = self._r[k]
                img = self._cache[idx]
                self._ref[k] = img
                self._disegnate[k].append(cv.create_image(7, y + self.CAP, anchor="nw", image=img))
                if idx == self._pag_sel:
                    self._disegnate[k].append(cv.create_rectangle(
                        5, y + self.CAP - 2, 9 + self.PW, y + h + 2, outline="#1a73e8", width=3
                    ))
            if len(self._disegnate) > 120:
                for k in [k for k in self._disegnate if k < a - 20 or k >= b + 20]:
                    for i in self._disegnate.pop(k):
                        cv.delete(i)
                    self._ref.pop(k, None)
        except Exception:
            pass

    def _rotella(self, ev):
        if getattr(ev, "num", None) == 4:
            d = -1
        elif getattr(ev, "num", None) == 5:
            d = 1
        else:
            d = -1 if ev.delta > 0 else 1
        self.cv.yview_scroll(d * 3, "units")


# ======================= divisione automatica per peso =======================
class Interrotto(Exception):
    """L'utente ha premuto Annulla durante la proposta di divisione."""


def parse_pagine_ripetute(testo, n_pagine):
    """'1' / '1-2, 5' -> [1, 2, 5] (in ordine, senza doppioni). Testo vuoto -> []."""
    if not testo.strip():
        return []
    pagine = set()
    for a, b in parse_ranges(testo, n_pagine):
        pagine.update(range(a, b + 1))
    return sorted(pagine)


def pagine_della_parte(a, b, ripeti):
    """Pagine (1-based) di una parte: prima quelle da ripetere che non stanno gia
    nell'intervallo a-b, poi a..b."""
    return [r for r in ripeti if not (a <= r <= b)] + list(range(a, b + 1))


def comprimi_pagine(pagine):
    """[1, 2, 3, 7] -> '1-3, 7'."""
    gruppi, inizio, prec = [], None, None
    for p in list(pagine) + [None]:
        if inizio is None:
            inizio = prec = p
        elif p is not None and p == prec + 1:
            prec = p
        else:
            gruppi.append(f"{inizio}-{prec}" if inizio != prec else str(inizio))
            inizio = prec = p
    return ", ".join(gruppi)


def costruisci_pagine(reader, pagine):
    """Byte del PDF con le pagine indicate (1-based) nell'ordine dato."""
    w = PdfWriter()
    for p in pagine:
        w.add_page(reader.pages[p - 1])
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _fine_massima(entra, s, n, guess):
    """Piu grande e in [s, n] tale che entra(s, e) sia vero; se neanche e = s entra,
    ritorna s (una pagina sola non si puo dividere ancora)."""
    lo = hi = None   # lo: fine che entra; hi: fine che NON entra
    e = max(s, min(n, s + guess - 1))
    while True:
        if entra(s, e):
            lo = e
        else:
            hi = e
        if lo is not None and hi is not None:
            if hi - lo <= 1:
                return lo
            e = (lo + hi) // 2
        elif lo is not None:             # finora entra: allunga
            if lo >= n:
                return n
            e = min(n, lo + max(1, (lo - s + 1) // 2))
        else:                            # finora non entra: accorcia
            if hi <= s:
                return s
            e = max(s, hi - max(1, (hi - s + 1) // 2))


def proponi_divisione(reader, max_kb, ripeti, kb_medio=None, avanzamento=None):
    """Parti consecutive, ognuna la piu lunga possibile senza superare max_kb (con le
    pagine da ripetere in testa). Ritorna [(a, b, kb, byte), ...]."""
    n = len(reader.pages)
    cache = {}

    def costruisci(s, e):
        if (s, e) not in cache:
            cache[(s, e)] = costruisci_pagine(reader, pagine_della_parte(s, e, ripeti))
        return cache[(s, e)]

    def entra(s, e):
        if avanzamento:
            avanzamento(f"Parte da pag. {s}: provo fino a pag. {e}...")
        return len(costruisci(s, e)) / 1024 <= max_kb

    parti, s = [], 1
    guess = max(1, int(max_kb / kb_medio)) if kb_medio else 10
    while s <= n:
        e = _fine_massima(entra, s, n, guess)
        dati = costruisci(s, e)
        parti.append((s, e, len(dati) / 1024, dati))
        for k in [k for k in cache if k[0] == s and k[1] != e]:
            del cache[k]   # tiene in memoria solo la parte scelta
        guess = max(1, e - s + 1)
        s = e + 1
    return parti


# ---------- riconoscimento visivo dell'inizio di ogni pratica (per scansioni) ----------
# Ogni pratica inizia con lo stesso modulo (stessi campi, dati diversi). Le pagine sono
# scansioni, quindi si confronta l'aspetto: miniatura in bianco/nero di ogni pagina,
# correlazione con la pagina modello (tollerando piccoli spostamenti e il capovolgimento
# di 180 gradi), poi si ripete con il modello medio degli inizi trovati.
from operator import mul

TW, TH = 40, 56   # miniatura (larghezza, altezza)
SH = 2            # spostamento tollerato, in pixel di miniatura

def miniature_pagine(percorso, blob, fitz_mod, avanzamento=None, interrompi=None):
    """Una miniatura 'inchiostro' (0 = bianco, 1 = nero) per pagina, come liste di righe."""
    doc = fitz_mod.open(stream=blob, filetype="pdf") if blob else fitz_mod.open(percorso)
    mini = []
    try:
        for i in range(len(doc)):
            if avanzamento:
                avanzamento(f"Analizzo pagina {i + 1} di {len(doc)}...")
            pg = doc[i]
            r = pg.rect
            m = fitz_mod.Matrix(TW / r.width, TH / r.height)
            pix = pg.get_pixmap(matrix=m, colorspace=fitz_mod.csGRAY, alpha=False)
            w, h, d = pix.width, pix.height, pix.samples
            righe = [[255 - d[y * w + x] for x in range(min(w, TW))] for y in range(min(h, TH))]
            mini.append(_normalizza(righe))
    finally:
        doc.close()
    return mini


def _normalizza(righe):
    """Toglie la media e porta la norma a 1 (cosi il prodotto scalare e una correlazione)."""
    h = len(righe)
    w = len(righe[0]) if h else 0
    tot = sum(map(sum, righe))
    media = tot / (w * h) if w * h else 0
    ris = [[v - media for v in r] for r in righe]
    norma = sum(v * v for r in ris for v in r) ** 0.5
    if norma < 1e-9:
        return [[0.0] * w for _ in range(h)]
    return [[v / norma for v in r] for r in ris]


def ruota180(m):
    return [r[::-1] for r in m[::-1]]


def somiglianza(a, b):
    """Correlazione massima tra due miniature, tollerando piccoli spostamenti."""
    h, w = len(a), len(a[0])
    best = -1.0
    for dy in range(-SH, SH + 1):
        ya0, yb0 = max(0, dy), max(0, -dy)
        n = h - abs(dy)
        for dx in range(-SH, SH + 1):
            xa0, xb0 = max(0, dx), max(0, -dx)
            k = w - abs(dx)
            s = 0.0
            for y in range(n):
                s += sum(map(mul, a[ya0 + y][xa0:xa0 + k], b[yb0 + y][xb0:xb0 + k]))
            if s > best:
                best = s
    return best


def punteggio(mini, modello):
    """Somiglianza di ogni pagina con il modello (anche capovolta di 180 gradi)."""
    mr = ruota180(modello)
    return [max(somiglianza(m, modello), somiglianza(m, mr)) for m in mini]


def soglia_automatica(punti):
    """Soglia di Otsu: separa i punteggi alti (inizi) da quelli bassi (altre pagine)."""
    s = sorted(punti)
    n = len(s)
    if n < 2:
        return 1.0
    migliore, soglia = -1.0, s[-1] + 1
    for k in range(1, n):
        if s[k] - s[k - 1] < 1e-9:
            continue
        m1, m2 = sum(s[:k]) / k, sum(s[k:]) / (n - k)
        var = k * (n - k) * (m1 - m2) ** 2
        if var > migliore:
            migliore, soglia = var, (s[k - 1] + s[k]) / 2
    return soglia


def soglia_bassa(punti, salto=0.05):
    """Dove finisce il 'mucchio' delle pagine non-inizio: primo salto >= `salto` tra i
    punteggi ordinati (ignorando il 20% piu basso: pagine bianche o strane). Cosi gli
    inizi molto vari restano tutti sopra la soglia."""
    s = sorted(punti)
    if len(s) < 3:
        return soglia_automatica(punti)
    da = len(s) // 5
    for x, y in zip(s[da:], s[da + 1:]):
        if y - x >= salto:
            return (x + y) / 2
    return soglia_automatica(punti)


def _media(mini, indici, modello):
    """Modello medio degli inizi gia trovati (ognuno orientato come il modello)."""
    mr = ruota180(modello)
    h, w = len(modello), len(modello[0])
    acc = [[0.0] * w for _ in range(h)]
    for i in indici:
        m = mini[i]
        if somiglianza(m, mr) > somiglianza(m, modello):
            m = ruota180(m)
        for y in range(h):
            ry, rm = acc[y], m[y]
            for x in range(w):
                ry[x] += rm[x]
    return _normalizza(acc)


def riconosci_inizi(mini, pagina_modello=1):
    """Pagine (1-based) che assomigliano alla pagina modello: prima con il modello
    scelto, poi ripetendo con il modello medio degli inizi trovati (piu affidabile).
    Ritorna (inizi, punteggi, soglia)."""
    modello = mini[pagina_modello - 1]
    punti = punteggio(mini, modello)
    soglia = soglia_bassa(punti)
    for _ in range(2):
        idx = [i for i, p in enumerate(punti) if p >= soglia]
        if not idx:
            break
        modello = _media(mini, idx, modello)
        punti = punteggio(mini, modello)
        soglia = soglia_bassa(punti)
    inizi = [i + 1 for i, p in enumerate(punti) if p >= soglia]
    return inizi, punti, soglia



def proponi_divisione_pratiche(reader, max_kb, ripeti, inizi, kb_medio=None, avanzamento=None):
    """Come proponi_divisione, ma taglia solo prima di una pagina di 'inizi' (1-based):
    ogni parte contiene pratiche intere. Una pratica che da sola supera max_kb resta
    in una parte sua (sara segnalata SOPRA). Ritorna [(a, b, kb, byte), ...]."""
    n = len(reader.pages)
    inizi = sorted({p for p in inizi if 1 <= p <= n} | {1})
    fini = [p - 1 for p in inizi[1:]] + [n]
    nu = len(inizi)
    cache = {}

    def costruisci(u, v):
        if (u, v) not in cache:
            cache[(u, v)] = costruisci_pagine(reader, pagine_della_parte(inizi[u], fini[v], ripeti))
        return cache[(u, v)]

    def entra(u, v):
        if avanzamento:
            avanzamento(f"Pratica {u + 1}: provo fino alla pratica {v + 1} (pag. {inizi[u]}-{fini[v]})...")
        return len(costruisci(u, v)) / 1024 <= max_kb

    parti, u = [], 0
    guess = max(1, int(max_kb / kb_medio / max(1, n / nu))) if kb_medio else 3
    while u < nu:
        v = _fine_massima(entra, u, nu - 1, guess)
        dati = costruisci(u, v)
        parti.append((inizi[u], fini[v], len(dati) / 1024, dati))
        for k in [k for k in cache if k[0] == u and k[1] != v]:
            del cache[k]
        guess = max(1, v - u + 1)
        u = v + 1
    return parti


class DividiPerPeso(FinestraBase):
    """Divide un PDF in parti sotto un peso massimo. Le pagine indicate (es. la copertina)
    vengono ripetute all'inizio di ogni parte. La divisione si propone in automatico e
    poi si puo correggere a mano."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Dividi per peso")
        # su schermi piccoli (portatili) la finestra non supera lo schermo
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(980, sw - 40)}x{min(800, sh - 110)}+{max(0, (sw - min(980, sw - 40)) // 2)}+10")
        self.minsize(min(760, sw - 40), min(480, sh - 110))
        self.reader = None
        self.n = 0
        self.nomi = {}       # (a, b) -> nome scelto
        self.parti = []      # [(a, b, kb, byte)]
        self._cache = {}     # (a, b, ripeti) -> byte
        self._annulla = False
        self._ripeti_usate = []
        self.var_file = tk.StringVar(value=master.var_file.get())
        self.var_max = tk.StringVar(value=master.var_max.get())
        self.var_ripeti = tk.StringVar()
        self.var_out = tk.StringVar(value=master.var_out.get())
        self.var_pratiche = tk.BooleanVar(value=False)
        self.var_modello = tk.StringVar(value="1")
        self.var_inizi = tk.StringVar()
        self._mini = None    # miniature delle pagine (riconoscimento inizi)

        ttk.Label(self, text="File PDF:").pack(anchor="w", padx=10, pady=(10, 0))
        r = ttk.Frame(self)
        r.pack(fill="x", padx=10)
        ttk.Entry(r, textvariable=self.var_file).pack(side="left", fill="x", expand=True)
        Btn(r, text="Sfoglia...", command=self.scegli_file).pack(side="left", padx=5)
        self.lbl_info = ttk.Label(self, text="Nessun file caricato")
        self.lbl_info.pack(anchor="w", padx=10, pady=(4, 0))

        r = ttk.Frame(self)
        r.pack(fill="x", padx=10, pady=(8, 0))
        ttk.Label(r, text="Peso massimo per parte (KB):").pack(side="left")
        ttk.Entry(r, textvariable=self.var_max, width=8).pack(side="left", padx=5)
        ttk.Label(r, text="   Pagine da ripetere all'inizio di ogni parte:").pack(side="left")
        ttk.Entry(r, textvariable=self.var_ripeti, width=12).pack(side="left", padx=5)
        ttk.Label(r, text="(es. 1  oppure  1-2; vuoto = nessuna)").pack(side="left")

        # taglia solo all'inizio di ogni pratica (scansioni con lo stesso modulo in testa)
        lf = ttk.LabelFrame(self, text="Taglia solo all'inizio di ogni pratica (riconoscimento visivo)")
        lf.pack(fill="x", padx=10, pady=(8, 0))
        r = ttk.Frame(lf)
        r.pack(fill="x", padx=6, pady=(4, 0))
        Chk(r, text="Usa gli inizi pratica", variable=self.var_pratiche).pack(side="left")
        ttk.Label(r, text="   Pagina modello (un inizio):").pack(side="left")
        ttk.Entry(r, textvariable=self.var_modello, width=5).pack(side="left", padx=5)
        Btn(r, text="Riconosci inizi", command=self.riconosci).pack(side="left", padx=8)
        self.lbl_inizi = ttk.Label(r, text="")
        self.lbl_inizi.pack(side="left")
        r = ttk.Frame(lf)
        r.pack(fill="x", padx=6, pady=(2, 6))
        ttk.Label(r, text="Pagine dove inizia una pratica (correggi a mano se serve):").pack(side="left")
        ttk.Entry(r, textvariable=self.var_inizi).pack(side="left", fill="x", expand=True, padx=5)

        r = ttk.Frame(self)
        r.pack(pady=8)
        Btn(r, text="Proponi divisione", command=self.proponi, height=2, width=20).pack(
            side="left", padx=5
        )
        Btn(r, text="Ricalcola dagli intervalli", command=self.ricalcola, height=2, width=25).pack(
            side="left", padx=5
        )
        Btn(r, text="Vedi nell'anteprima", command=self.vedi_in_principale, height=2, width=21).pack(
            side="left", padx=5
        )
        Btn(r, text="Annulla", command=self._ferma, height=2, width=10).pack(side="left", padx=5)

        ttk.Label(self, text="Intervalli (puoi correggerli e premere Ricalcola):").pack(anchor="w", padx=10)
        self.txt = tk.Text(self, height=3)
        self.txt.pack(fill="x", padx=10)
        self._stile_testo()

        # parte bassa impacchettata PRIMA (dal fondo): i pulsanti restano sempre visibili
        # e la tabella usa solo lo spazio che avanza
        r = ttk.Frame(self)
        r.pack(side="bottom", pady=8)
        Btn(r, text="Crea i file", command=self.crea, height=2, width=18).pack(side="left", padx=5)
        Btn(r, text="Chiudi", command=self.destroy, height=2, width=10).pack(side="left", padx=5)
        r = ttk.Frame(self)
        r.pack(side="bottom", fill="x", padx=10)
        ttk.Entry(r, textvariable=self.var_out).pack(side="left", fill="x", expand=True)
        Btn(r, text="Sfoglia...", command=self.scegli_out).pack(side="left", padx=5)
        ttk.Label(self, text="Cartella di destinazione:").pack(side="bottom", anchor="w", padx=10, pady=(4, 0))
        self.lbl_nota = ttk.Label(self, text="", anchor="w", justify="left", wraplength=900)
        self.lbl_nota.pack(side="bottom", fill="x", padx=10, pady=(4, 0))

        ttk.Label(self, text="Doppio clic su una riga per cambiare il nome del file:").pack(
            anchor="w", padx=10, pady=(6, 0)
        )
        cont = ttk.Frame(self)
        cont.pack(fill="both", expand=True, padx=10)
        self.tree = Albero(cont, columns=("n", "pagine", "kb", "stato", "nome"), show="headings", height=5)
        for col, testo, larg in (
            ("n", "N.", 40), ("pagine", "Pagine", 150), ("kb", "KB", 80),
            ("stato", "Stato", 160), ("nome", "Nome file", 380),
        ):
            self.tree.heading(col, text=testo)
            self.tree.column(col, width=larg, anchor="w")
        self._tag_risultati()
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(cont, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", self.rinomina_riga)


        if self.var_file.get() and os.path.isfile(self.var_file.get()):
            self._carica(self.var_file.get())

    # ---------- tema ----------
    def _tag_risultati(self):
        pal = tavolozza()
        self.tree.tag_configure("ok", foreground=pal["ok"])
        self.tree.tag_configure("over", foreground=pal["over"])

    def _stile_testo(self):
        if e_scuro():
            self.txt.config(bg="#2b2b2b", fg="#e8e8e8", insertbackground="white",
                            highlightthickness=1, highlightbackground="#5d656d")
        else:
            self.txt.config(bg="white", fg="black", insertbackground="black",
                            highlightthickness=1, highlightbackground="#b0b0b0")

    def applica_tema(self):
        self.aggiorna_sfondo()
        self._tag_risultati()
        self._stile_testo()

    # ---------- file ----------
    def _carica(self, p):
        try:
            reader = PdfReader(p)
            if reader.is_encrypted and not reader.decrypt(""):
                raise ValueError("Il PDF e protetto da password")
            n = len(reader.pages)
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile aprire il PDF:\n{e}", parent=self)
            return
        self.reader, self.n, self.nomi, self.parti, self._cache = reader, n, {}, [], {}
        self._mini = None
        self.var_inizi.set("")
        self.lbl_inizi.config(text="")
        self.var_file.set(p)
        if not self.var_out.get():
            self.var_out.set(os.path.dirname(p))
        self.lbl_info.config(text=f"{n} pagine - {os.path.getsize(p) / 1024:,.0f} KB")
        self.tree.delete(*self.tree.get_children())
        self.lbl_nota.config(text="")

    def scegli_file(self):
        p = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")], parent=self)
        if p:
            self.var_out.set(os.path.dirname(p))
            self._carica(p)

    def scegli_out(self):
        d = filedialog.askdirectory(parent=self)
        if d:
            self.var_out.set(d)

    # ---------- parametri ----------
    def _leggi_parametri(self):
        if not self.reader:
            messagebox.showwarning("Attenzione", "Scegli prima un file PDF.", parent=self)
            return None
        try:
            max_kb = float(self.var_max.get().replace(",", "."))
            if max_kb <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Errore", "Inserisci un peso massimo valido in KB (es. 4500).", parent=self)
            return None
        try:
            ripeti = parse_pagine_ripetute(self.var_ripeti.get(), self.n)
        except ValueError as e:
            messagebox.showerror("Errore", f"Pagine da ripetere: {e}", parent=self)
            return None
        if ripeti:
            kb_rip = len(costruisci_pagine(self.reader, ripeti)) / 1024
            if kb_rip >= max_kb:
                messagebox.showerror(
                    "Errore",
                    f"Le pagine da ripetere ({comprimi_pagine(ripeti)}) pesano {kb_rip:,.0f} KB: "
                    f"da sole raggiungono il limite di {max_kb:,.0f} KB.",
                    parent=self,
                )
                return None
        return max_kb, ripeti

    def _ferma(self):
        self._annulla = True

    def _avanza(self, testo):
        self.lbl_nota.config(text=testo)
        self.update()
        if self._annulla:
            raise Interrotto()

    # ---------- inizi pratica ----------
    def _leggi_inizi(self):
        """Pagine di inizio pratica scritte nel campo (lista ordinata) o None se errore."""
        try:
            return parse_pagine_ripetute(self.var_inizi.get(), self.n)
        except ValueError as e:
            messagebox.showerror("Errore", f"Inizi pratica: {e}", parent=self)
            return None

    def riconosci(self):
        if not self.reader:
            messagebox.showwarning("Attenzione", "Scegli prima un file PDF.", parent=self)
            return
        if fitz is None:
            messagebox.showerror(
                "Manca PyMuPDF",
                "Il riconoscimento visivo richiede PyMuPDF:  pip install pymupdf", parent=self,
            )
            return
        try:
            modello = int(self.var_modello.get())
            if not 1 <= modello <= self.n:
                raise ValueError
        except ValueError:
            messagebox.showerror("Errore", f"Pagina modello: un numero da 1 a {self.n}.", parent=self)
            return
        self._annulla = False
        self.config(cursor="watch")
        try:
            if self._mini is None:
                self._mini = miniature_pagine(self.var_file.get(), None, fitz, self._avanza)
            inizi, punti, soglia = riconosci_inizi(self._mini, modello)
        except Interrotto:
            self.lbl_nota.config(text="Riconoscimento annullato.")
            return
        except tk.TclError:
            return
        except Exception as e:
            messagebox.showerror("Errore", str(e), parent=self)
            return
        finally:
            try:
                self.config(cursor="")
            except tk.TclError:
                pass
        self.var_inizi.set(comprimi_pagine(inizi))
        self.var_pratiche.set(True)
        self.lbl_inizi.config(text=f"{len(inizi)} pratiche trovate")
        self.lbl_nota.config(
            text=f"Riconosciuti {len(inizi)} inizi pratica (modello: pag. {modello}). "
                 "Controllali nel campo qui sopra: puoi aggiungere o togliere pagine, poi premi 'Proponi divisione'."
        )

    # ---------- proposta e ricalcolo ----------
    def proponi(self):
        dati = self._leggi_parametri()
        if dati is None:
            return
        max_kb, ripeti = dati
        inizi = None
        if self.var_pratiche.get():
            inizi = self._leggi_inizi()
            if inizi is None:
                return
            if not inizi:
                messagebox.showwarning(
                    "Inizi pratica", "Premi prima 'Riconosci inizi' (o scrivi le pagine di inizio).", parent=self
                )
                return
        kb_medio = os.path.getsize(self.var_file.get()) / 1024 / max(self.n, 1)
        self._annulla = False
        self.config(cursor="watch")
        try:
            if inizi is not None:
                parti = proponi_divisione_pratiche(self.reader, max_kb, ripeti, inizi, kb_medio, self._avanza)
            else:
                parti = proponi_divisione(self.reader, max_kb, ripeti, kb_medio, self._avanza)
        except Interrotto:
            self.lbl_nota.config(text="Proposta annullata.")
            return
        except tk.TclError:
            return   # finestra chiusa durante il calcolo
        except Exception as e:
            messagebox.showerror("Errore", str(e), parent=self)
            return
        finally:
            try:
                self.config(cursor="")
            except tk.TclError:
                pass
        for a, b, kb, dati_pdf in parti:
            self._cache[(a, b, tuple(ripeti))] = dati_pdf
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", ", ".join(f"{a}-{b}" if a != b else str(a) for a, b, _, _ in parti))
        self._mostra(parti, max_kb, ripeti)

    def ricalcola(self):
        dati = self._leggi_parametri()
        if dati is None:
            return None
        max_kb, ripeti = dati
        try:
            intervalli = parse_ranges(self.txt.get("1.0", "end"), self.n)
        except ValueError as e:
            messagebox.showerror("Errore", str(e), parent=self)
            return None
        self.config(cursor="watch")
        self.update()
        try:
            parti = []
            for a, b in intervalli:
                chiave = (a, b, tuple(ripeti))
                if chiave not in self._cache:
                    self._cache[chiave] = costruisci_pagine(self.reader, pagine_della_parte(a, b, ripeti))
                dati_pdf = self._cache[chiave]
                parti.append((a, b, len(dati_pdf) / 1024, dati_pdf))
        except Exception as e:
            messagebox.showerror("Errore", str(e), parent=self)
            return None
        finally:
            self.config(cursor="")
        self._mostra(parti, max_kb, ripeti)
        return parti

    def vedi_in_principale(self):
        """Porta gli intervalli nella finestra principale: l'anteprima a destra mostra
        tutte le pagine con i confini e il peso di ogni parte, e si puo scorrere."""
        parti = self.ricalcola()
        if not parti:
            return
        try:
            if os.path.abspath(self.master.var_file.get()) != os.path.abspath(self.var_file.get()):
                if not self.master._carica_pdf(self.var_file.get(), None, self):
                    return
            self.master.var_max.set(self.var_max.get())
            self.master.txt_range.delete("1.0", "end")
            self.master.txt_range.insert("1.0", self.txt.get("1.0", "end").strip())
            self.master.anteprima()
            self.master.lift()
        except Exception as e:
            messagebox.showerror("Errore", str(e), parent=self)
            return
        if self._ripeti_usate:
            self.lbl_nota.config(
                text="Anteprima aperta nella finestra principale (le pagine ripetute non sono incluse nei pesi mostrati lì)."
            )

    def _nome_predefinito(self, i, a, b):
        base = os.path.splitext(os.path.basename(self.var_file.get()))[0]
        return f"{base}_parte{i}_p{a}-{b}.pdf"

    def _nome_per(self, i, a, b):
        return self.nomi.get((a, b)) or self._nome_predefinito(i, a, b)

    def _mostra(self, parti, max_kb, ripeti):
        self.parti, self._ripeti_usate = parti, ripeti
        self.tree.delete(*self.tree.get_children())
        sopra = 0
        for i, (a, b, kb, _) in enumerate(parti):
            if kb <= max_kb:
                stato, tag = "OK", "ok"
            else:
                stato, tag = f"SOPRA di {kb - max_kb:,.0f} KB", "over"
                sopra += 1
            pag = f"{a}-{b}" if a != b else str(a)
            fuori = [r for r in ripeti if not (a <= r <= b)]
            if fuori:
                pag = f"{comprimi_pagine(fuori)} + {pag}"
            self.tree.insert(
                "", "end", iid=str(i), tags=(tag, "zebra") if i % 2 else (tag,),
                values=(i + 1, pag, f"{kb:,.0f}", stato, self._nome_per(i + 1, a, b)),
            )
        note = [f"{len(parti)} parti, totale {sum(p[2] for p in parti):,.0f} KB."]
        if ripeti:
            note.append(f"Pagine ripetute in testa a ogni parte: {comprimi_pagine(ripeti)}.")
        if sopra:
            note.append(
                f"{sopra} parte/i sopra il limite: contengono una pagina sola, che da sola non entra."
                if all(p[0] == p[1] for p in parti if p[2] > max_kb)
                else f"{sopra} parte/i sopra il limite."
            )
        mancanti = pagine_non_incluse([(a, b) for a, b, _, _ in parti], self.n)
        if mancanti:
            note.append(f"Pagine non incluse in nessun intervallo: {mancanti}.")
        self.lbl_nota.config(text=" ".join(note))

    def rinomina_riga(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        i = int(iid)
        a, b, _, _ = self.parti[i]
        nuovo = simpledialog.askstring(
            "Rinomina", f"Nome del file per le pagine {a}-{b}:",
            initialvalue=self._nome_per(i + 1, a, b), parent=self,
        )
        if nuovo is None:
            return
        try:
            self.nomi[(a, b)] = pulisci_nome(nuovo)
        except ValueError as e:
            messagebox.showerror("Errore", str(e), parent=self)
            return
        self.tree.set(iid, "nome", self.nomi[(a, b)])

    # ---------- salvataggio ----------
    def crea(self):
        parti = self.ricalcola()   # parte sempre dagli intervalli scritti: niente file "vecchi"
        if not parti:
            return
        max_kb = float(self.var_max.get().replace(",", "."))
        out = self.var_out.get() or os.path.dirname(self.var_file.get())
        try:
            sopra = [p for p in parti if p[2] > max_kb]
            if sopra:
                elenco = "\n".join(f"- pagine {a}-{b}: {kb:,.0f} KB" for a, b, kb, _ in sopra)
                if not messagebox.askyesno(
                    "Parti sopra il limite",
                    f"Queste parti superano {max_kb:,.0f} KB:\n\n{elenco}\n\nCreare i file lo stesso?",
                    parent=self,
                ):
                    return
            nomi = [self._nome_per(i + 1, a, b) for i, (a, b, _, _) in enumerate(parti)]
            doppi = {x for x in nomi if nomi.count(x) > 1}
            if doppi:
                messagebox.showerror(
                    "Nomi uguali", "Due parti hanno lo stesso nome file:\n" + "\n".join(sorted(doppi)),
                    parent=self,
                )
                return
            os.makedirs(out, exist_ok=True)
            esistenti = [x for x in nomi if os.path.exists(os.path.join(out, x))]
            if esistenti and not messagebox.askyesno(
                "File esistenti",
                "Questi file esistono gia e verrebbero sovrascritti:\n\n" + "\n".join(esistenti)
                + "\n\nSovrascrivere?",
                parent=self,
            ):
                return
            for (a, b, kb, dati_pdf), nome in zip(parti, nomi):
                with open(os.path.join(out, nome), "wb") as f:
                    f.write(dati_pdf)
            div_id = salva_divisione(
                self.master.conn,
                os.path.basename(self.var_file.get()),
                self.n,
                os.path.getsize(self.var_file.get()) / 1024,
                out,
                [(i + 1, a, b, kb, nome, d) for i, ((a, b, kb, d), nome) in enumerate(zip(parti, nomi))],
            )
            self.lbl_nota.config(text=f"Creati {len(nomi)} file in {out} - salvati nel DB e nello storico (n. {div_id})")
            messagebox.showinfo(
                "Fatto", f"Creati {len(nomi)} file in:\n{out}\n\nSalvati sia su disco che nel database.", parent=self
            )
        except Exception as e:
            messagebox.showerror("Errore", str(e), parent=self)


class FinestraInfo(FinestraBase):
    """Informazioni sul programma, contatto e licenze."""

    def __init__(self, master):
        super().__init__(master)
        self.title(f"Informazioni su {APP_NOME}")
        self.transient(master)
        self.resizable(False, False)
        ttk.Label(self, text=APP_NOME, font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=20, pady=(18, 0))
        ttk.Label(self, text=f"Versione {APP_VERSIONE}").pack(anchor="w", padx=20)
        ttk.Label(
            self, justify="left", wraplength=480,
            text="Divide i PDF in parti sotto un peso massimo, riconosce l'inizio di ogni pratica "
                 "nelle scansioni, riordina e unisce le pagine e tiene lo storico delle divisioni. "
                 "Funziona interamente sul tuo computer: nessun documento viene inviato online.",
        ).pack(anchor="w", padx=20, pady=(10, 0))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=20, pady=12)
        ttk.Label(self, text=f"Autore: {APP_AUTORE}").pack(anchor="w", padx=20)
        ttk.Label(
            self, justify="left", wraplength=480,
            text="Per consulti e lavori su richiesta scrivimi via email:",
        ).pack(anchor="w", padx=20, pady=(6, 0))
        r = ttk.Frame(self)
        r.pack(anchor="w", padx=20, pady=(4, 0))
        Btn(r, text="Scrivimi", command=self.scrivi, width=12).pack(side="left")
        Btn(r, text="Copia email", command=self.copia, width=13).pack(side="left", padx=6)
        ttk.Label(r, text=APP_EMAIL).pack(side="left", padx=6)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=20, pady=12)
        ttk.Label(self, text=f"Licenza del programma: {APP_LICENZA}").pack(anchor="w", padx=20)
        ttk.Label(
            self, justify="left",
            text="Librerie usate:  " + ";  ".join(f"{n} ({l})" for n, l in APP_LIBRERIE),
            wraplength=480,
        ).pack(anchor="w", padx=20, pady=(2, 0))
        ttk.Label(
            self, justify="left", wraplength=480,
            text="Software fornito cosi com'e, senza garanzie di alcun tipo. "
                 "Controlla sempre i file prodotti prima di usarli.",
        ).pack(anchor="w", padx=20, pady=(8, 0))
        Btn(self, text="Chiudi", command=self.destroy, width=10).pack(anchor="e", padx=20, pady=16)
        self.update_idletasks()
        try:
            self.geometry(f"+{master.winfo_rootx() + 80}+{master.winfo_rooty() + 60}")
        except tk.TclError:
            pass

    def scrivi(self):
        try:
            webbrowser.open(f"mailto:{APP_EMAIL}?subject={APP_NOME.replace(' ', '%20')}")
        except Exception:
            self.copia()

    def copia(self):
        self.clipboard_clear()
        self.clipboard_append(APP_EMAIL)
        messagebox.showinfo("Email", f"Indirizzo copiato:\n{APP_EMAIL}", parent=self)


class FinestraDatabase(FinestraBase):
    """Piccola finestra per scegliere il database dello storico (anche su cartella condivisa
    di rete), controllarlo e ricordare la scelta."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Seleziona database")
        self.transient(master)
        self.resizable(False, False)
        self.var_nuovo = tk.StringVar(value=leggi_percorso_db())
        self.var_usato = tk.StringVar()
        self.var_info = tk.StringVar()

        ttk.Label(self, text="Database in uso:").pack(anchor="w", padx=12, pady=(12, 0))
        ttk.Label(self, textvariable=self.var_usato, wraplength=560, justify="left").pack(
            anchor="w", padx=12
        )
        ttk.Label(self, textvariable=self.var_info).pack(anchor="w", padx=12, pady=(2, 0))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=12, pady=10)

        ttk.Label(self, text="Database da usare (file .db, anche su cartella condivisa):").pack(
            anchor="w", padx=12
        )
        r = ttk.Frame(self)
        r.pack(fill="x", padx=12)
        ttk.Entry(r, textvariable=self.var_nuovo, width=58).pack(side="left", fill="x", expand=True)
        Btn(r, text="Sfoglia...", command=self.sfoglia).pack(side="left", padx=(6, 0))
        r = ttk.Frame(self)
        r.pack(fill="x", padx=12, pady=(6, 0))
        Btn(r, text="Nuovo database...", command=self.nuovo).pack(side="left")
        Btn(r, text="Usa quello locale", command=self.usa_locale).pack(side="left", padx=6)

        ttk.Label(
            self, justify="left", wraplength=560,
            text="Su una cartella di rete il database funziona se il server e raggiungibile. "
                 "Se due persone salvano nello stesso istante puo comparire 'database is locked': "
                 "basta riprovare dopo qualche secondo.",
        ).pack(anchor="w", padx=12, pady=(10, 0))

        r = ttk.Frame(self)
        r.pack(fill="x", padx=12, pady=12)
        Btn(r, text="Chiudi", command=self.destroy, width=10).pack(side="right")
        Btn(r, text="Salva e usa", command=self.salva, width=14).pack(side="right", padx=(0, 6))

        self._aggiorna()
        self.update_idletasks()
        try:
            self.geometry(f"+{master.winfo_rootx() + 60}+{master.winfo_rooty() + 60}")
        except tk.TclError:
            pass

    @staticmethod
    def _descrivi(conn, percorso):
        n_div = conn.execute("SELECT COUNT(*) FROM divisioni").fetchone()[0]
        n_parti = conn.execute("SELECT COUNT(*) FROM parti").fetchone()[0]
        try:
            kb = os.path.getsize(percorso) / 1024
            quando = datetime.fromtimestamp(os.path.getmtime(percorso)).strftime("%d/%m/%Y %H:%M")
            return f"{n_div} divisioni, {n_parti} parti - {kb:,.0f} KB - ultima modifica {quando}"
        except OSError:
            return f"{n_div} divisioni, {n_parti} parti"

    def _percorso_in_uso(self):
        try:
            for _, nome, file in self.master.conn.execute("PRAGMA database_list"):
                if nome == "main" and file:
                    return file
        except sqlite3.Error:
            pass
        return ""

    def _aggiorna(self):
        p = self._percorso_in_uso()
        self.var_usato.set(p or "(database in memoria)")
        try:
            self.var_info.set(self._descrivi(self.master.conn, p) if p else "")
        except sqlite3.Error as e:
            self.var_info.set(str(e))

    def sfoglia(self):
        p = filedialog.askopenfilename(
            parent=self, title="Scegli il database",
            filetypes=[("Database SQLite", "*.db *.sqlite *.sqlite3"), ("Tutti i file", "*.*")],
        )
        if p:
            self.var_nuovo.set(os.path.normpath(p))

    def nuovo(self):
        p = filedialog.asksaveasfilename(
            parent=self, title="Crea un nuovo database", defaultextension=".db",
            initialfile="dividi_pdf.db", filetypes=[("Database SQLite", "*.db")],
        )
        if p:
            self.var_nuovo.set(os.path.normpath(p))
            self.salva()

    def usa_locale(self):
        if self._cambia(""):
            self.var_nuovo.set("")

    def salva(self):
        p = self.var_nuovo.get().strip().strip('"')
        if not p:
            messagebox.showwarning(
                "Database", "Scegli un file con Sfoglia... oppure usa quello locale.", parent=self
            )
            return
        self._cambia(p)

    def _cambia(self, percorso):
        """Apre il database indicato; se funziona diventa quello in uso e la scelta si ricorda."""
        if percorso and not os.path.isfile(percorso):
            if not os.path.isdir(os.path.dirname(percorso) or "."):
                messagebox.showerror(
                    "Database", f"La cartella non esiste o non e raggiungibile:\n{os.path.dirname(percorso)}",
                    parent=self,
                )
                return False
            if not messagebox.askyesno(
                "Database", "Il file non esiste: lo creo come nuovo database vuoto?", parent=self
            ):
                return False
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            nuova = apri_db(percorso or None)
        except Exception as e:
            messagebox.showerror("Database", f"Non riesco ad aprire il database:\n{e}", parent=self)
            return False
        finally:
            try:
                self.config(cursor="")
            except tk.TclError:
                pass
        vecchia = self.master.conn
        self.master.conn = nuova
        try:
            vecchia.close()
        except sqlite3.Error:
            pass
        if not salva_percorso_db(percorso):
            messagebox.showwarning(
                "Database", "Database cambiato, ma non sono riuscito a ricordare la scelta per la prossima volta.",
                parent=self,
            )
        self._aggiorna()
        messagebox.showinfo(
            "Database",
            "Ora il programma usa questo database.\nSe lo Storico e aperto, chiudilo e riaprilo per vedere i dati nuovi.",
            parent=self,
        )
        return True


class App(ttkb.Window if ttkb else tk.Tk):
    def __init__(self):
        if ttkb:
            self._tema = leggi_tema()
            super().__init__(themename=self._tema)
            ttkb.Style().configure("Treeview", rowheight=26)
        else:
            super().__init__()
        self.title("PDF Smart Splitter")
        self.geometry("1260x760")
        self._ripristina_finestra()
        self.protocol("WM_DELETE_WINDOW", self._chiudi)
        self.n_pagine = 0
        self.reader = None
        self.cache = {}
        self.nomi = {}
        self.righe = []
        self.conn, self._avviso_db = self._apri_db_scelto()

        self.var_file = tk.StringVar()
        self.var_out = tk.StringVar()
        self.var_max = tk.StringVar(value="4500")
        self.var_top = tk.BooleanVar(value=False)
        self._occupato = False
        self.var_stato = tk.StringVar(value="Pronto")

        self.var_sb_file = tk.StringVar(value="Nessun file caricato")
        self.var_sb_parti = tk.StringVar(value="Nessun intervallo")
        barra_stato = ttk.Frame(self)
        barra_stato.pack(side="bottom", fill="x")
        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x")
        ttk.Label(barra_stato, textvariable=self.var_sb_file, anchor="w").pack(
            side="left", padx=10, pady=3
        )
        ttk.Label(barra_stato, textvariable=self.var_sb_parti, anchor="e").pack(
            side="right", padx=10, pady=3
        )

        self.prev = AnteprimaDivisione(self)
        self.prev.pack(side="right", fill="y", padx=(0, 10), pady=10)

        self._zona_bordo, self._zona_sfondo = tavolozza()["zona_bordo"], tavolozza()["zona_sfondo"]
        self._testo_zona = ""
        self.cv_drop = tk.Canvas(
            self, height=54, highlightthickness=0
        )
        self.cv_drop.pack(fill="x", padx=10, pady=(10, 0))
        self.cv_drop.bind("<Configure>", lambda e: self._disegna_zona())
        self._aggiorna_zona()

        ttk.Label(self, text="File PDF:").pack(anchor="w", padx=10, pady=(10, 0))
        riga = ttk.Frame(self)
        riga.pack(fill="x", padx=10)
        ttk.Entry(riga, textvariable=self.var_file).pack(side="left", fill="x", expand=True)
        Btn(riga, text="Sfoglia...", command=self.scegli_file).pack(side="left", padx=5)

        self.lbl_info = ttk.Label(self, text="Nessun file caricato")
        self.lbl_info.pack(anchor="w", padx=10, pady=(4, 0))

        ttk.Label(
            self, text="Intervalli di pagine (es. 1-88, 89-200, 201-300):"
        ).pack(anchor="w", padx=10, pady=(10, 0))
        self.txt_range = tk.Text(self, height=3)
        self.txt_range.pack(fill="x", padx=10)

        riga_max = ttk.Frame(self)
        riga_max.pack(fill="x", padx=10, pady=(8, 0))
        ttk.Label(riga_max, text="Peso massimo per parte (KB):").pack(side="left")
        ttk.Entry(riga_max, textvariable=self.var_max, width=8).pack(side="left", padx=5)
        Chk(
            riga_max, text="Tieni la finestra in primo piano (per trascinare i PDF)",
            variable=self.var_top,
            command=lambda: self.attributes("-topmost", self.var_top.get()),
        ).pack(side="left", padx=15)

        ttk.Label(self, text="Cartella di destinazione:").pack(anchor="w", padx=10, pady=(8, 0))
        riga2 = ttk.Frame(self)
        riga2.pack(fill="x", padx=10)
        ttk.Entry(riga2, textvariable=self.var_out).pack(side="left", fill="x", expand=True)
        Btn(riga2, text="Sfoglia...", command=self.scegli_out).pack(side="left", padx=5)

        botti = ttk.Frame(self)
        botti.pack(pady=8)
        # gruppo 1: la divisione a mano; gruppo 2: gli altri strumenti
        Btn(botti, text="Anteprima peso", command=self.anteprima, height=2, width=15).pack(
            side="left", padx=4
        )
        Btn(botti, text="Crea i file", command=self.crea, height=2, width=15).pack(
            side="left", padx=4
        )
        ttk.Separator(botti, orient="vertical").pack(side="left", fill="y", padx=12, pady=2)
        Btn(
            botti, text="Dividi per peso...", command=self.apri_dividi_peso, height=2, width=17
        ).pack(side="left", padx=4)
        Btn(
            botti, text="Modifica / Unisci PDF", command=self.apri_editor, height=2, width=19
        ).pack(side="left", padx=4)
        Btn(botti, text="Storico", command=self.apri_storico, height=2, width=11).pack(
            side="left", padx=4
        )

        riga_prog = ttk.Frame(self)
        riga_prog.pack(fill="x", padx=10, pady=(0, 6))
        self.progress = ttk.Progressbar(riga_prog, mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)
        ttk.Label(
            riga_prog, textvariable=self.var_stato, width=24, anchor="e"
        ).pack(side="left", padx=(8, 0))

        ttk.Label(
            self, text="Doppio clic su una riga per cambiare il nome del file:"
        ).pack(anchor="w", padx=10)
        cont = ttk.Frame(self)
        cont.pack(fill="both", expand=True, padx=10)
        colonne = ("n", "pagine", "kb", "stato", "barra", "nome")
        self.tree = Albero(cont, columns=colonne, show="headings", height=8)
        for col, testo, larg in (
            ("n", "N.", 40),
            ("pagine", "Pagine", 110),
            ("kb", "KB", 80),
            ("stato", "Stato", 150),
            ("barra", "Peso rispetto al limite", 170),
            ("nome", "Nome file", 300),
        ):
            self.tree.heading(col, text=testo)
            self.tree.column(col, width=larg, anchor="w")
        self._tag_risultati()
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(cont, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", self.rinomina_riga)

        self.lbl_nota = ttk.Label(self, text="", anchor="w", justify="left")
        self.lbl_nota.pack(fill="x", padx=10, pady=(4, 8))

        self.txt_range.bind("<KeyRelease>", lambda e: self._pianifica_marcatori())
        self.var_max.trace_add("write", lambda *a: self._pianifica_marcatori())
        self.tree.bind("<<TreeviewSelect>>", self._vai_a_parte)
        self._kb_storico = {}
        self._crea_menu()
        if self._avviso_db:
            self.after(600, lambda: messagebox.showwarning("Database", self._avviso_db, parent=self))
        self._applica_tavolozza()

    def me_scegli_file(self):
        p = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not p:
            return
        try:
            reader = PdfReader(p)
            n = len(reader.pages)
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile aprire il PDF:\n{e}")
            return
        self.reader, self.n_pagine, self.cache, self.nomi = reader, n, {}, {}
        self.var_file.set(p)
        self.var_out.set(os.path.dirname(p))
        kb = os.path.getsize(p) / 1024
        self.lbl_info.config(text=f"{n} pagine - {kb:,.0f} KB")
        self._svuota_tabella()
        self.prev.carica(p)
        self._aggiorna_zona()
        self._kb_storico = {}
        self._aggiorna_marcatori()

    scegli_file = me_scegli_file

    def me_scegli_out(self):
        d = filedialog.askdirectory()
        if d:
            self.var_out.set(d)

    scegli_out = me_scegli_out

    def _svuota_tabella(self):
        self.tree.delete(*self.tree.get_children())
        self.righe = []
        self.lbl_nota.config(text="")

    def _aggiorna_barra_stato(self, parti=None):
        if parti is not None:
            self._parti_sb = parti
        p = self.var_file.get()
        if self.reader and p:
            try:
                kb = os.path.getsize(p) / 1024
            except OSError:
                kb = 0
            self.var_sb_file.set(
                f"{os.path.basename(p)}  -  {self.n_pagine} pagine  -  {kb:,.0f} KB"
            )
        else:
            self.var_sb_file.set("Nessun file caricato")
        ps = getattr(self, "_parti_sb", [])
        if not ps:
            self.var_sb_parti.set("Nessun intervallo")
            return
        testo = f"{len(ps)} parti"
        noti = [q["kb"] for q in ps if q["kb"] is not None]
        if len(noti) == len(ps):
            testo += f"  -  totale {sum(noti):,.0f} KB"
        sopra = sum(1 for q in ps if q["stato"] == "over")
        if sopra:
            testo += f"  -  {sopra} sopra il limite"
        self.var_sb_parti.set(testo)

    def _crea_menu(self):
        barra = tk.Menu(self)

        m_file = tk.Menu(barra, tearoff=0)
        m_file.add_command(label="Apri PDF...", command=self.scegli_file, accelerator="Ctrl+O")
        m_file.add_command(label="Cartella di destinazione...", command=self.scegli_out)
        m_file.add_separator()
        m_file.add_command(label="Modifica / Unisci PDF", command=self.apri_editor)
        m_file.add_command(label="Dividi per peso...", command=self.apri_dividi_peso)
        m_file.add_command(label="Storico divisioni", command=self.apri_storico, accelerator="Ctrl+H")
        m_file.add_command(label="Seleziona database...", command=self.apri_selettore_db)
        m_file.add_separator()
        m_file.add_command(label="Esci", command=self._chiudi)
        barra.add_cascade(label="File", menu=m_file)

        m_str = tk.Menu(barra, tearoff=0)
        m_str.add_command(label="Anteprima peso", command=self.anteprima)
        m_str.add_command(label="Crea i file", command=self.crea)
        m_str.add_separator()
        m_str.add_checkbutton(
            label="Tieni la finestra in primo piano", variable=self.var_top,
            command=lambda: self.attributes("-topmost", self.var_top.get()),
        )
        barra.add_cascade(label="Strumenti", menu=m_str)

        if ttkb:
            self.var_tema = tk.StringVar(value=self._tema)
            m_tema = tk.Menu(barra, tearoff=0)
            for gruppo, nomi in (("Chiari", TEMI_CHIARI), ("Scuri", TEMI_SCURI)):
                if gruppo == "Scuri":
                    m_tema.add_separator()
                m_tema.add_command(label=gruppo, state="disabled")
                for nome in nomi:
                    m_tema.add_radiobutton(
                        label=nome.capitalize(), value=nome, variable=self.var_tema,
                        command=lambda n=nome: self.cambia_tema(n),
                    )
            barra.add_cascade(label="Tema", menu=m_tema)

        m_info = tk.Menu(barra, tearoff=0)
        m_info.add_command(label=f"Informazioni su {APP_NOME}", command=lambda: FinestraInfo(self))
        barra.add_cascade(label="?", menu=m_info)

        self.config(menu=barra)
        self.bind("<Control-o>", lambda e: self.scegli_file())
        self.bind("<Control-h>", lambda e: self.apri_storico())

    def _tag_risultati(self):
        pal = tavolozza()
        self.tree.tag_configure("ok", foreground=pal["ok"])
        self.tree.tag_configure("over", foreground=pal["over"])

    def cambia_tema(self, nome):
        if not ttkb:
            return
        try:
            ttkb.Style().theme_use(nome)
        except Exception:
            return
        self._tema = nome
        if hasattr(self, "var_tema"):
            self.var_tema.set(nome)
        ttkb.Style().configure("Treeview", rowheight=26)
        salva_tema(nome)
        self._applica_tavolozza()

    def _applica_tavolozza(self):
        pal = tavolozza()
        self._zona_bordo, self._zona_sfondo = pal["zona_bordo"], pal["zona_sfondo"]
        
        bg_col = ttkb.Style().colors.bg if ttkb else ("#222222" if e_scuro() else "#f8f9fa")
        
        try:
            self.cv_drop.configure(bg=bg_col)
        except tk.TclError:
            pass
            
        if hasattr(self, 'txt_range'):
            if e_scuro():
                self.txt_range.config(
                    bg="#2b2b2b", fg="#e8e8e8", insertbackground="white", highlightthickness=1, highlightbackground="#5d656d"
                )
            else:
                self.txt_range.config(
                    bg="white", fg="black", insertbackground="black", highlightthickness=1, highlightbackground="#b0b0b0"
                )

        self._disegna_zona()
        self._tag_risultati()
        ricolora_alberi()
        ricolora_bottoni()
        self.prev.applica_tema()
        for w in self.winfo_children():
            if isinstance(w, FinestraBase):
                w.applica_tema()

    def _ripristina_finestra(self):
        imp = leggi_impostazioni()
        g = imp.get("geometria")
        m = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", g) if isinstance(g, str) else None
        if m:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            w, h, x, y = (int(v) for v in m.groups())
            w, h = max(700, min(w, sw)), max(500, min(h, sh))
            if -w + 120 <= x <= sw - 120 and 0 <= y <= sh - 80:
                self.geometry(f"{w}x{h}+{x}+{y}")
            else:
                self.geometry(f"{w}x{h}")
        if imp.get("zoomed"):
            try:
                self.state("zoomed")
            except tk.TclError:
                pass

    def _apri_db_scelto(self):
        """Apre il database scelto in 'Seleziona database'; se non e raggiungibile
        (es. server spento) usa quello locale e lo segnala. Ritorna (conn, avviso)."""
        p = leggi_percorso_db()
        if p:
            try:
                return apri_db(p), None
            except Exception as e:
                return apri_db(), (
                    f"Il database scelto non e raggiungibile:\n{p}\n\n{e}\n\n"
                    "Sto usando il database locale. Puoi cambiarlo da File > Seleziona database."
                )
        return apri_db(), None

    def apri_selettore_db(self):
        FinestraDatabase(self)

    def _chiudi(self):
        try:
            imp = leggi_impostazioni()
            if self.state() == "zoomed":
                imp["zoomed"] = True
            else:
                imp["zoomed"] = False
                imp["geometria"] = self.geometry()
            salva_impostazioni(imp)
        except Exception:
            pass
        self.destroy()

    def _aggiorna_zona(self):
        if self.reader and self.var_file.get():
            nome = os.path.basename(self.var_file.get())
            self._testo_zona = (
                f"\u2714  {nome}  -  {self.n_pagine} pagine\n"
                "(trascina qui un altro PDF per sostituirlo)"
            )
        else:
            self._testo_zona = (
                "\u2B07  Trascina qui un PDF per caricarlo\n(oppure usa Sfoglia...)"
            )
        self._disegna_zona()
        self._aggiorna_barra_stato()

    def _disegna_zona(self, bordo=None, sfondo=None):
        cv = self.cv_drop
        bordo = bordo or self._zona_bordo
        sfondo = sfondo or self._zona_sfondo
        cv.delete("all")
        w = max(cv.winfo_width(), 100)
        h = int(cv["height"])
        cv.create_rectangle(3, 3, w - 4, h - 4, outline=bordo, fill=sfondo, width=2, dash=(6, 4))
        cv.create_text(
            w // 2, h // 2, text=self._testo_zona, fill=tavolozza()["zona_testo"],
            justify="center", font=("Segoe UI", 10),
        )

    def _lampeggia_zona(self):
        pal = tavolozza()
        self._disegna_zona(pal["zona_ok_bordo"], pal["zona_ok_sfondo"])
        self.after(700, self._disegna_zona)

    def _drop_pdf(self, files):
        if self._occupato:
            return
        if self._carica_pdf(files[0], n_atteso=None, parent=self):
            self._lampeggia_zona()

    def _progresso(self, valore, testo=None):
        try:
            self.progress["value"] = valore
            if testo is not None:
                self.var_stato.set(testo)
            self.update()
        except tk.TclError:
            pass

    def _reset_progresso(self):
        if not self._occupato:
            self._progresso(0, "Pronto")

    def _nome_predefinito(self, i, a, b):
        base = os.path.splitext(os.path.basename(self.var_file.get()))[0]
        return f"{base}_parte{i}_p{a}-{b}.pdf"

    def _nome_per(self, i, a, b):
        return self.nomi.get((a, b)) or self._nome_predefinito(i, a, b)

    def rinomina_riga(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        i = int(iid)
        a, b, _ = self.righe[i]
        attuale = self._nome_per(i + 1, a, b)
        nuovo = simpledialog.askstring(
            "Rinomina", f"Nome del file per le pagine {a}-{b}:", initialvalue=attuale, parent=self
        )
        if nuovo is None:
            return
        try:
            self.nomi[(a, b)] = pulisci_nome(nuovo)
        except ValueError as e:
            messagebox.showerror("Errore", str(e))
            return
        self.tree.set(iid, "nome", self.nomi[(a, b)])

    def _leggi_input(self):
        if not self.reader:
            messagebox.showwarning("Attenzione", "Scegli prima un file PDF.")
            return None
        try:
            max_kb = float(self.var_max.get().replace(",", "."))
            if max_kb <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Errore", "Inserisci un peso massimo valido in KB (es. 4500).")
            return None
        try:
            intervalli = parse_ranges(self.txt_range.get("1.0", "end"), self.n_pagine)
        except ValueError as e:
            messagebox.showerror("Errore", str(e))
            return None
        return intervalli, max_kb

    def _misura(self, intervalli, max_kb, quota=100):
        gia = self._occupato
        self._occupato = True
        self.config(cursor="watch")
        try:
            self._progresso(0, "Calcolo del peso...")
            self._svuota_tabella()
            da_fare = sum(b - a + 1 for a, b in intervalli if (a, b) not in self.cache)
            fatte = [0]

            def pagina_fatta():
                fatte[0] += 1
                if fatte[0] % 5 == 0 or fatte[0] == da_fare:
                    self._progresso(
                        quota * 0.9 * fatte[0] / max(da_fare, 1),
                        f"Pagine {fatte[0]}/{da_fare}",
                    )

            for i, (a, b) in enumerate(intervalli):
                if (a, b) not in self.cache:
                    self.cache[(a, b)] = costruisci_parte(self.reader, a, b, pagina_fatta)
                kb = len(self.cache[(a, b)]) / 1024
                self.righe.append((a, b, kb))
                if kb <= max_kb:
                    stato, tag = "OK", "ok"
                else:
                    stato, tag = f"SOPRA di {kb - max_kb:,.0f} KB", "over"
                pag = f"{a}-{b}" if a != b else str(a)
                self.tree.insert(
                    "", "end", iid=str(i), tags=(tag, "zebra") if i % 2 else (tag,),
                    values=(
                        i + 1, pag, f"{kb:,.0f}", stato, barra_peso(kb, max_kb),
                        self._nome_per(i + 1, a, b),
                    ),
                )
            mancanti = pagine_non_incluse(intervalli, self.n_pagine)
            if mancanti:
                self.lbl_nota.config(text=f"Pagine non incluse in nessun intervallo: {mancanti}")
            self._aggiorna_marcatori()
            self._progresso(quota, f"Calcolate {len(intervalli)} parti")
            return list(self.righe)
        finally:
            self._occupato = gia
            self.config(cursor="")
            if quota == 100 and not gia:
                self.after(2500, self._reset_progresso)

    def anteprima(self):
        if self._occupato:
            return
        dati = self._leggi_input()
        if dati is None:
            return
        try:
            self._misura(*dati)
        except Exception as e:
            messagebox.showerror("Errore", str(e))

    def crea(self):
        if self._occupato:
            return
        self._occupato = True
        try:
            self._crea_interno()
        finally:
            self._occupato = False
            self.after(2500, self._reset_progresso)

    def _crea_interno(self):
        dati = self._leggi_input()
        if dati is None:
            return
        intervalli, max_kb = dati
        out = self.var_out.get() or os.path.dirname(self.var_file.get())
        try:
            risultati = self._misura(*dati, quota=60)
            sopra = [r for r in risultati if r[2] > max_kb]
            if sopra:
                elenco = "\n".join(f"- pagine {a}-{b}: {kb:,.0f} KB" for a, b, kb in sopra)
                if not messagebox.askyesno(
                    "Parti sopra il limite",
                    f"Queste parti superano {max_kb:,.0f} KB:\n\n{elenco}\n\nCreare i file lo stesso?",
                ):
                    return
            nomi = [self._nome_per(i + 1, a, b) for i, (a, b, _) in enumerate(risultati)]
            doppi = {n for n in nomi if nomi.count(n) > 1}
            if doppi:
                messagebox.showerror(
                    "Nomi uguali", "Due parti hanno lo stesso nome file:\n" + "\n".join(sorted(doppi))
                )
                return
            os.makedirs(out, exist_ok=True)
            esistenti = [n for n in nomi if os.path.exists(os.path.join(out, n))]
            if esistenti and not messagebox.askyesno(
                "File esistenti",
                "Questi file esistono gia e verrebbero sovrascritti:\n\n"
                + "\n".join(esistenti)
                + "\n\nSovrascrivere?",
            ):
                return
            tot_f = len(risultati)
            for k, ((a, b, kb), nome) in enumerate(zip(risultati, nomi), 1):
                with open(os.path.join(out, nome), "wb") as f:
                    f.write(self.cache[(a, b)])
                self._progresso(60 + 35 * k / tot_f, f"Scrittura file {k}/{tot_f}")
            self._progresso(97, "Salvataggio nello storico...")
            
            div_id = salva_divisione(
                self.conn,
                os.path.basename(self.var_file.get()),
                self.n_pagine,
                os.path.getsize(self.var_file.get()) / 1024,
                out,
                [
                    (i + 1, a, b, kb, nome, self.cache[(a, b)])
                    for i, ((a, b, kb), nome) in enumerate(zip(risultati, nomi))
                ],
            )
            self.lbl_nota.config(text=f"Creati {len(nomi)} file in {out} - salvati nel DB e nello storico (n. {div_id})")
            self._progresso(100, "Completato")
            messagebox.showinfo("Fatto", f"Creati {len(nomi)} file in:\n{out}\n\nSalvati sia su disco che nel database.")
        except Exception as e:
            messagebox.showerror("Errore", str(e))

    def _carica_pdf(self, p, n_atteso, parent):
        try:
            reader = PdfReader(p)
            n = len(reader.pages)
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile aprire il PDF:\n{e}", parent=parent)
            return False
        if n_atteso and n != n_atteso and not messagebox.askyesno(
            "Pagine diverse",
            f"Questo PDF ha {n} pagine, la divisione salvata ne aveva {n_atteso}.\n\nCaricarlo lo stesso?",
            parent=parent,
        ):
            return False
        self.reader, self.n_pagine, self.cache, self.nomi = reader, n, {}, {}
        self.var_file.set(p)
        self.var_out.set(os.path.dirname(p))
        kb = os.path.getsize(p) / 1024
        self.lbl_info.config(text=f"{n} pagine - {kb:,.0f} KB")
        self._svuota_tabella()
        self.prev.carica(p)
        self._aggiorna_zona()
        return True

    def _ricarica_pdf_origine(self, did, parent):
        self._kb_storico = {}
        riga = self.conn.execute(
            "SELECT pdf_origine, n_pagine, cartella FROM divisioni WHERE id = ?", (did,)
        ).fetchone()
        if not riga or riga[0].startswith("Modifica:"):
            return
        nome, n_pag, cartella = riga
        pronto = (
            bool(self.reader)
            and os.path.basename(self.var_file.get()) == nome
            and self.n_pagine == n_pag
        )
        if not pronto:
            candidati = [os.path.join(cartella, nome)]
            if self.var_file.get():
                candidati.append(os.path.join(os.path.dirname(self.var_file.get()), nome))
            percorso = next((c for c in candidati if os.path.isfile(c)), None)
            if not percorso:
                opzioni = {"parent": parent, "title": f"Dov'e il PDF originale '{nome}'?",
                           "initialfile": nome, "filetypes": [("PDF", "*.pdf")]}
                if os.path.isdir(cartella):
                    opzioni["initialdir"] = cartella
                percorso = filedialog.askopenfilename(**opzioni)
            if not percorso or not self._carica_pdf(percorso, n_pag, parent):
                self.lbl_nota.config(
                    text=f"PDF originale '{nome}' non caricato: scegli il file con Sfoglia... per vedere l'anteprima"
                )
                return
            if os.path.isdir(cartella):
                self.var_out.set(cartella)
        self._kb_storico = {
            (a, b): kb
            for a, b, kb in self.conn.execute(
                "SELECT pag_da, pag_a, kb FROM parti WHERE divisione_id = ?", (did,)
            )
        }

    def _pianifica_marcatori(self):
        if getattr(self, "_marc_id", None) is None:
            self._marc_id = self.after(350, self._aggiorna_marcatori)

    def _aggiorna_marcatori(self):
        self._marc_id = None
        if not self.reader:
            return
        testo = self.txt_range.get("1.0", "end")
        if not testo.strip():
            intervalli = []
        else:
            try:
                intervalli = parse_ranges(testo, self.n_pagine)
            except ValueError:
                return
        try:
            max_kb = float(self.var_max.get().replace(",", "."))
        except ValueError:
            max_kb = None
        kb_noti = None
        if len(self.righe) == len(intervalli) and all(
            (a, b) == (r[0], r[1]) for (a, b), r in zip(intervalli, self.righe)
        ):
            kb_noti = [r[2] for r in self.righe]
        parti = []
        for i, (a, b) in enumerate(intervalli):
            kb = kb_noti[i] if kb_noti else None
            da_storico = False
            if kb is None and (a, b) in self._kb_storico:
                kb, da_storico = self._kb_storico[(a, b)], True
            if kb is None:
                stato = "nd"
            else:
                stato = "ok" if (max_kb is None or kb <= max_kb) else "over"
            parti.append({"a": a, "b": b, "kb": kb, "stato": stato, "max": max_kb, "storico": da_storico})
        self.prev.imposta_parti(parti)
        self._aggiorna_barra_stato(parti)

    def _vai_a_parte(self, event=None):
        sel = self.tree.selection()
        if sel:
            try:
                self.prev.vai_a_parte(int(sel[0]))
            except ValueError:
                pass

    def apri_editor(self):
        EditorPDF(self, self.var_file.get() or None)

    def apri_dividi_peso(self):
        DividiPerPeso(self)

    def apri_storico(self):
        win = FinestraBase(self)
        win.title("Storico divisioni")
        win.geometry("1060x520")
        win.transient(self)

        var_anno = tk.StringVar(value="Tutti")
        var_mese = tk.StringVar(value="Tutti")
        var_cerca = tk.StringVar()

        filtro = ttk.Frame(win)
        filtro.pack(fill="x", padx=10, pady=(10, 0))
        
        ttk.Label(filtro, text="Anno:").pack(side="left")
        cb_anno = ttk.Combobox(filtro, textvariable=var_anno, state="readonly", width=7)
        cb_anno.pack(side="left", padx=(2, 8))
        
        ttk.Label(filtro, text="Mese:").pack(side="left")
        cb_mese = ttk.Combobox(
            filtro, textvariable=var_mese, state="readonly", width=10, values=["Tutti"] + MESI
        )
        cb_mese.pack(side="left", padx=(2, 8))

        ttk.Label(filtro, text="Cerca (Nome file):").pack(side="left", padx=(8, 2))
        txt_cerca = ttk.Entry(filtro, textvariable=var_cerca, width=20)
        txt_cerca.pack(side="left", padx=(0, 5))
        
        lbl_conta = ttk.Label(filtro, text="")
        lbl_conta.pack(side="right")

        colonne = ("data", "pdf", "n", "pagine", "kb", "nome", "cartella")
        tree = Albero(win, columns=colonne, show="headings")
        for col, testo, larg in (
            ("data", "Data", 110),
            ("pdf", "PDF origine", 170),
            ("n", "N.", 35),
            ("pagine", "Pagine", 80),
            ("kb", "KB", 65),
            ("nome", "Nome file", 280),
            ("cartella", "Cartella", 230),
        ):
            tree.heading(col, text=testo)
            tree.column(col, width=larg, anchor="w")
        # barra pulsanti impacchettata PRIMA, in fondo: resta sempre visibile
        barra = ttk.Frame(win)
        barra.pack(side="bottom", fill="x", padx=10, pady=(8, 10))
        tree.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        mappa = {}

        def ricarica():
            anni = ["Tutti"] + anni_disponibili(self.conn)
            cb_anno["values"] = anni
            if var_anno.get() not in anni:
                var_anno.set("Tutti")
            anno = None if var_anno.get() == "Tutti" else int(var_anno.get())
            mese = None if var_mese.get() == "Tutti" else MESI.index(var_mese.get()) + 1
            testo = var_cerca.get().strip() or None

            tree.delete(*tree.get_children())
            mappa.clear()
            righe = elenco_storico(self.conn, anno, mese, testo)
            for (pid, did, data, pdf, num, a, b, kb, nome, cart) in righe:
                iid = tree.insert(
                    "", "end", tags=("zebra",) if len(tree.get_children()) % 2 else (),
                    values=(data, pdf, num, f"{a}-{b}" if a != b else a, f"{kb:,.0f}", nome, cart),
                )
                mappa[iid] = (pid, did)
            n_div = len({r[1] for r in righe})
            if righe:
                lbl_conta.config(text=f"{n_div} divisioni - {len(righe)} parti")
            elif anno or mese or testo:
                lbl_conta.config(text="Nessun risultato")
            else:
                lbl_conta.config(text="Storico vuoto")

        def azzera_filtri():
            var_anno.set("Tutti")
            var_mese.set("Tutti")
            var_cerca.set("")
            ricarica()

        cb_anno.bind("<<ComboboxSelected>>", lambda e: ricarica())
        cb_mese.bind("<<ComboboxSelected>>", lambda e: ricarica())
        txt_cerca.bind("<KeyRelease>", lambda e: ricarica())
        Btn(filtro, text="Mostra Tutti", command=azzera_filtri).pack(side="left", padx=5)

        def selezionata():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Storico", "Seleziona prima una riga.", parent=win)
                return None
            return sel[0]

        def rinomina():
            iid = selezionata()
            if iid is None:
                return
            pid, _ = mappa[iid]
            attuale = tree.set(iid, "nome")
            nuovo = simpledialog.askstring(
                "Rinomina", "Nuovo nome del file:", initialvalue=attuale, parent=win
            )
            if nuovo is None:
                return
            try:
                _, trovato = rinomina_parte(self.conn, pid, nuovo)
            except (ValueError, OSError) as e:
                messagebox.showerror("Errore", str(e), parent=win)
                return
            ricarica()
            if not trovato:
                messagebox.showinfo(
                    "Storico",
                    "Nome aggiornato nel database, ma il file non era piu nella cartella.",
                    parent=win,
                )

        def ricarica_intervalli():
            iid = selezionata()
            if iid is None:
                return
            _, did = mappa[iid]
            self._ricarica_pdf_origine(did, win)
            self.txt_range.delete("1.0", "end")
            self.txt_range.insert("1.0", intervalli_divisione(self.conn, did))
            self._aggiorna_marcatori()
            win.destroy()

        def elimina():
            iid = selezionata()
            if iid is None:
                return
            _, did = mappa[iid]
            if messagebox.askyesno(
                "Elimina dallo storico",
                "Tolgo questa divisione dallo storico.\nI file PDF sul disco NON vengono cancellati.\n\nProcedo?",
                parent=win,
            ):
                elimina_divisione(self.conn, did)
                ricarica()

        def ripristina_pdf_da_db(parte_id, percorso):
            riga = self.conn.execute("SELECT pdf_blob FROM parti WHERE id = ?", (parte_id,)).fetchone()
            if riga and riga[0]:
                os.makedirs(os.path.dirname(percorso), exist_ok=True)
                with open(percorso, "wb") as f:
                    f.write(riga[0])
                return True
            return False

        def percorso_selezionato():
            iid = selezionata()
            if iid is None:
                return None
            pid, _ = mappa[iid]
            cartella = tree.set(iid, "cartella")
            nome = tree.set(iid, "nome")
            percorso = os.path.join(cartella, nome)
            
            if not os.path.exists(percorso):
                if not ripristina_pdf_da_db(pid, percorso):
                    messagebox.showinfo(
                        "File non trovato",
                        f"Il file non e presente su disco e non e presente alcun backup nel database:\n\n{percorso}",
                        parent=win,
                    )
                    return None
            return percorso

        def apri_pdf(event=None):
            percorso = percorso_selezionato()
            if percorso:
                try:
                    apri_con_sistema(percorso)
                except OSError as e:
                    messagebox.showerror("Errore", f"Impossibile aprire il file:\n{e}", parent=win)

        def apri_cartella():
            percorso = percorso_selezionato()
            if percorso:
                try:
                    mostra_in_cartella(percorso)
                except OSError as e:
                    messagebox.showerror("Errore", f"Impossibile aprire la cartella:\n{e}", parent=win)

        tree.bind("<Double-1>", apri_pdf)

        gr_file = ttk.LabelFrame(barra, text="Sul file selezionato")
        gr_file.pack(side="left", padx=(0, 10))
        Btn(gr_file, text="Apri PDF", command=apri_pdf, width=11).pack(side="left", padx=5, pady=5)
        Btn(gr_file, text="Apri cartella", command=apri_cartella, width=13).pack(side="left", padx=5, pady=5)
        Btn(gr_file, text="Rinomina file...", command=rinomina, width=15).pack(side="left", padx=5, pady=5)
        gr_div = ttk.LabelFrame(barra, text="Sulla divisione selezionata")
        gr_div.pack(side="left")
        Btn(gr_div, text="Ricarica questi intervalli", command=ricarica_intervalli, width=23).pack(
            side="left", padx=5, pady=5
        )
        Btn(gr_div, text="Elimina dallo storico", command=elimina, width=19).pack(side="left", padx=5, pady=5)
        Btn(barra, text="Chiudi", command=win.destroy, width=9).pack(side="right", anchor="s", pady=5)
        ricarica()


def _abilita_dnd_nativo_win(widget, callback):
    if not sys.platform.startswith("win"):
        return

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    HDROP = wintypes.HANDLE

    LRESULT = ctypes.c_ssize_t
    WPARAM = ctypes.c_size_t
    LPARAM = ctypes.c_ssize_t

    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND,
                                       wintypes.UINT, WPARAM, LPARAM]
    user32.CallWindowProcW.restype = LRESULT

    shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
    shell32.DragQueryFileW.argtypes = [HDROP, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell32.DragQueryFileW.restype = wintypes.UINT
    shell32.DragFinish.argtypes = [HDROP]

    WM_DROPFILES = 0x0233
    WM_COPYGLOBALDATA = 0x0049
    MSGFLT_ALLOW = 1
    state = {"old": None}

    def wndproc(hwnd, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            hdrop = HDROP(wparam)
            files = []
            try:
                n = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                for i in range(n):
                    lung = shell32.DragQueryFileW(hdrop, i, None, 0)
                    buf = ctypes.create_unicode_buffer(lung + 1)
                    shell32.DragQueryFileW(hdrop, i, buf, lung + 1)
                    p = buf.value.strip()
                    if p.lower().endswith(".pdf") and os.path.isfile(p):
                        files.append(p)
            except Exception:
                pass
            finally:
                shell32.DragFinish(hdrop)
            if files:
                widget.after(10, lambda f=files: callback(f))
            return 0
        return user32.CallWindowProcW(state["old"], hwnd, msg, wparam, lparam)

    hwnd = user32.GetParent(widget.winfo_id()) or widget.winfo_id()

    try:
        user32.ChangeWindowMessageFilterEx.argtypes = [wintypes.HWND, wintypes.UINT,
                                                       wintypes.DWORD, ctypes.c_void_p]
        for m in (WM_DROPFILES, WM_COPYGLOBALDATA):
            user32.ChangeWindowMessageFilterEx(hwnd, m, MSGFLT_ALLOW, None)
    except Exception:
        pass

    shell32.DragAcceptFiles(hwnd, True)

    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)
    new_wndproc = WNDPROC(wndproc)

    GWLP_WNDPROC = -4
    SetWindowLongPtr = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    SetWindowLongPtr.restype = ctypes.c_void_p

    old = SetWindowLongPtr(hwnd, GWLP_WNDPROC, new_wndproc)
    if not old:
        shell32.DragAcceptFiles(hwnd, False)
        return
    state["old"] = old
    widget._dnd_callback = new_wndproc


def _avvia_app_con_dnd():
    app = App()
    try:
        app.after(200, lambda: _abilita_dnd_nativo_win(
            app, app._drop_pdf))
    except Exception:
        pass
    app.mainloop()


if __name__ == "__main__":
    _avvia_app_con_dnd()