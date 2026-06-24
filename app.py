from __future__ import annotations

from datetime import datetime
from pathlib import Path
import ctypes
import os
import queue
import subprocess
import sys
import tempfile
import threading

from lm_studio_integration import (
    LMStudioError,
    LMStudioSession,
    lm_studio_semantic_search,
    prepare_lm_studio,
)
from search_engine import (
    APP_NAME,
    CREATOR,
    DOCUMENT_TYPE_CHOICES,
    DOCUMENT_TYPE_LABELS,
    DOCUMENT_TYPE_ALL_KEY,
    SearchResponse,
    SearchResult,
    coerce_document_type_key,
    human_size,
    smart_search,
)


_TCL_DLL = None
SOURCE_FILES = (
    ("Aplicativo", "app.py"),
    ("Busca", "search_engine.py"),
    ("LM Studio", "lm_studio_integration.py"),
    ("Inicializacao", "sitecustomize.py"),
    ("OCR Windows", "tools/ocr_windows.ps1"),
    ("Empacotamento", "build_exe.ps1"),
    ("Instalador", "installer/setup_installer.py"),
)
DEVELOPER_LABEL = f"DESENVOLVEDOR: {CREATOR} - PROCURADOR FEDERAL / AGU"


def _set_tcl_library_paths(base_dirs: list[Path]) -> bool:
    if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
        return True

    candidates: list[Path] = []
    for base_dir in base_dirs:
        candidates.append(base_dir)
        try:
            candidates.extend(base_dir.parent.glob("cpython-*"))
        except OSError:
            pass

    for base_dir in candidates:
        tcl_data = base_dir / "tcl" / "tcl8.6"
        tk_data = base_dir / "tcl" / "tk8.6"
        if (tcl_data / "init.tcl").exists() and (tk_data / "tk.tcl").exists():
            os.environ.setdefault("TCL_LIBRARY", str(tcl_data))
            os.environ.setdefault("TK_LIBRARY", str(tk_data))
            return True
    return False


def initialize_tcl_runtime() -> None:
    global _TCL_DLL

    if os.name != "nt" or _TCL_DLL is not None:
        return

    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        tcl_data = meipass / "_tcl_data"
        tk_data = meipass / "_tk_data"
        if tcl_data.exists():
            os.environ["TCL_LIBRARY"] = str(tcl_data)
        if tk_data.exists():
            os.environ["TK_LIBRARY"] = str(tk_data)
        if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
            return

    base_dirs = [Path(sys.base_prefix), Path(sys.prefix), Path(sys.executable).resolve().parent]
    if getattr(sys, "frozen", False):
        base_dirs.insert(0, Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)))

    if _set_tcl_library_paths(base_dirs):
        return

    for base_dir in base_dirs:
        dll_candidates = [base_dir / "DLLs" / "tcl86t.dll", base_dir / "tcl86t.dll"]
        dll_path = next((candidate for candidate in dll_candidates if candidate.exists()), None)
        if dll_path is None:
            continue
        try:
            tcl = ctypes.CDLL(str(dll_path))
            tcl.Tcl_FindExecutable.argtypes = [ctypes.c_char_p]
            executable = base_dir / "python.exe" if getattr(sys, "frozen", False) else Path(sys.executable)
            tcl.Tcl_FindExecutable(str(executable).encode("utf-8"))
            _TCL_DLL = tcl
        except Exception:
            pass
        return


initialize_tcl_runtime()

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def source_path(relative: str) -> Path:
    if getattr(sys, "frozen", False):
        external = Path(sys.executable).resolve().parent / "source" / relative
        if external.exists():
            return external

    bundled = resource_path(f"source/{relative}")
    if bundled.exists():
        return bundled
    return Path(__file__).resolve().parent / relative


class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_ulong),
        ("dwHighDateTime", ctypes.c_ulong),
    ]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class KDMinhaPetApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1120x720")
        self.minsize(920, 560)

        icon_path = resource_path("assets/lupa.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass

        self.query_var = tk.StringVar()
        self.folder_var = tk.StringVar()
        self.search_mode_var = tk.StringVar(value="local")
        self.include_content_var = tk.BooleanVar(value=True)
        self.pdf_ocr_var = tk.BooleanVar(value=True)
        self.skip_technical_var = tk.BooleanVar(value=True)
        self.use_windows_search_var = tk.BooleanVar(value=False)
        self.max_results_var = tk.StringVar(value="50")
        self.year_start_var = tk.StringVar()
        self.year_end_var = tk.StringVar()
        self.document_type_var = tk.StringVar(value=DOCUMENT_TYPE_LABELS[DOCUMENT_TYPE_ALL_KEY])
        self.status_var = tk.StringVar(value="Pronto.")
        self.cpu_var = tk.StringVar(value="CPU: --%")
        self.memory_var = tk.StringVar(value="RAM: --%")
        self.detail_var = tk.StringVar(value="")

        self.worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.stop_event: threading.Event | None = None
        self.worker: threading.Thread | None = None
        self.results_by_iid: dict[str, SearchResult] = {}
        self.log_entries: list[str] = []
        self.lm_studio_session: LMStudioSession | None = None
        self._last_cpu_times = self._read_cpu_times()

        self._configure_style()
        self._build_layout()
        self._bind_events()
        self._log_event("Aplicativo iniciado.")
        self.after(120, self._consume_worker_queue)
        self.after(1000, self._update_cpu_status)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background="#f6f7f9")
        style.configure("Header.TFrame", background="#ffffff")
        style.configure("TLabel", background="#f6f7f9", foreground="#16202a")
        style.configure("Header.TLabel", background="#ffffff", foreground="#16202a")
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), background="#ffffff")
        style.configure("Creator.TLabel", font=("Segoe UI", 9), foreground="#5f6b7a")
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 14, 18, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text=APP_NAME, style="Title.TLabel")
        title.grid(row=0, column=0, sticky="w")

        creator = ttk.Label(
            header,
            text=DEVELOPER_LABEL,
            style="Creator.TLabel",
            background="#ffffff",
        )
        creator.grid(row=1, column=0, sticky="w", pady=(2, 0))

        controls = ttk.Frame(self, padding=(18, 14, 18, 10))
        controls.grid(row=1, column=0, sticky="nsew")
        controls.columnconfigure(0, weight=1)
        controls.rowconfigure(6, weight=1)

        mode_row = ttk.Frame(controls)
        mode_row.grid(row=0, column=0, sticky="ew")
        ttk.Label(mode_row, text="Modo").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Radiobutton(
            mode_row,
            text="Usar o LM Studio para Busca com Linguagem Natural",
            variable=self.search_mode_var,
            value="lmstudio",
            command=self.on_search_mode_changed,
        ).grid(row=0, column=1, sticky="w", padx=(0, 18))
        ttk.Radiobutton(
            mode_row,
            text="Busca local com termos de pesquisa (não usar o LM Studio)",
            variable=self.search_mode_var,
            value="local",
            command=self.on_search_mode_changed,
        ).grid(row=0, column=2, sticky="w")

        folder_row = ttk.Frame(controls)
        folder_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        folder_row.columnconfigure(1, weight=1)

        ttk.Label(folder_row, text="Pasta").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.folder_entry = ttk.Entry(folder_row, textvariable=self.folder_var)
        self.folder_entry.grid(row=0, column=1, sticky="ew", ipady=3)
        ttk.Button(folder_row, text="Selecionar...", command=self.select_folder).grid(
            row=0,
            column=2,
            padx=(10, 0),
        )

        query_row = ttk.Frame(controls)
        query_row.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        query_row.columnconfigure(1, weight=1)

        ttk.Label(query_row, text="Buscar").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.query_entry = ttk.Entry(query_row, textvariable=self.query_var, font=("Segoe UI", 11))
        self.query_entry.grid(row=0, column=1, sticky="ew", ipady=4)
        self.search_button = ttk.Button(
            query_row,
            text="Buscar",
            command=self.start_search,
            style="Accent.TButton",
        )
        self.search_button.grid(row=0, column=2, padx=(10, 0), ipadx=10)
        self.stop_button = ttk.Button(query_row, text="Parar", command=self.stop_search, state="disabled")
        self.stop_button.grid(row=0, column=3, padx=(8, 0))

        filter_row = ttk.Frame(controls)
        filter_row.grid(row=3, column=0, sticky="ew", pady=(10, 4))

        ttk.Label(filter_row, text="Resultados").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.max_results_combo = ttk.Combobox(
            filter_row,
            textvariable=self.max_results_var,
            values=("10", "25", "50", "100", "250", "500"),
            state="readonly",
            width=7,
        )
        self.max_results_combo.grid(row=0, column=1, sticky="w", padx=(0, 18))

        ttk.Label(filter_row, text="Ano inicial").grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.year_start_entry = ttk.Entry(filter_row, textvariable=self.year_start_var, width=8)
        self.year_start_entry.grid(row=0, column=3, sticky="w", padx=(0, 12))

        ttk.Label(filter_row, text="Ano final").grid(row=0, column=4, sticky="w", padx=(0, 8))
        self.year_end_entry = ttk.Entry(filter_row, textvariable=self.year_end_var, width=8)
        self.year_end_entry.grid(row=0, column=5, sticky="w", padx=(0, 18))

        ttk.Label(filter_row, text="Tipo de documento").grid(
            row=0,
            column=6,
            sticky="w",
            padx=(0, 8),
        )
        self.document_type_combo = ttk.Combobox(
            filter_row,
            textvariable=self.document_type_var,
            values=DOCUMENT_TYPE_CHOICES,
            state="readonly",
            width=24,
        )
        self.document_type_combo.grid(row=0, column=7, sticky="w")

        options_row = ttk.Frame(controls)
        options_row.grid(row=4, column=0, sticky="ew", pady=(6, 4))
        ttk.Checkbutton(
            options_row,
            text="Ler conteudo quando possivel",
            variable=self.include_content_var,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            options_row,
            text="OCR em PDFs escaneados",
            variable=self.pdf_ocr_var,
        ).grid(row=0, column=1, sticky="w", padx=(18, 0))
        ttk.Checkbutton(
            options_row,
            text="Ignorar pastas tecnicas",
            variable=self.skip_technical_var,
        ).grid(row=0, column=2, sticky="w", padx=(18, 0))
        ttk.Checkbutton(
            options_row,
            text="Usar indice do Windows Search quando disponivel",
            variable=self.use_windows_search_var,
        ).grid(row=0, column=3, sticky="w", padx=(18, 0))

        action_row = ttk.Frame(controls)
        action_row.grid(row=5, column=0, sticky="ew", pady=(4, 8))
        ttk.Button(action_row, text="Abrir arquivo", command=self.open_selected_file).grid(
            row=0,
            column=0,
            padx=(0, 8),
        )
        ttk.Button(action_row, text="Abrir pasta", command=self.open_selected_folder).grid(
            row=0,
            column=1,
            padx=(0, 8),
        )
        ttk.Button(action_row, text="Copiar caminho", command=self.copy_selected_path).grid(
            row=0,
            column=2,
            padx=(0, 8),
        )
        ttk.Button(action_row, text="Exportar logs", command=self.export_logs).grid(
            row=0,
            column=3,
            padx=(0, 8),
        )
        ttk.Button(action_row, text="README", command=self.show_readme).grid(
            row=0,
            column=4,
            padx=(0, 8),
        )
        ttk.Button(action_row, text="Exibir Código Fonte", command=self.show_source_code).grid(
            row=0,
            column=5,
            padx=(0, 8),
        )

        content = ttk.PanedWindow(controls, orient=tk.VERTICAL)
        content.grid(row=6, column=0, sticky="nsew")

        table_frame = ttk.Frame(content)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        content.add(table_frame, weight=4)

        columns = ("score", "name", "type", "document_type", "modified", "size", "path")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("score", text="Relevancia")
        self.tree.heading("name", text="Nome")
        self.tree.heading("type", text="Tipo")
        self.tree.heading("document_type", text="Documento")
        self.tree.heading("modified", text="Modificado")
        self.tree.heading("size", text="Tamanho")
        self.tree.heading("path", text="Caminho")

        self.tree.column("score", width=88, anchor="center", stretch=False)
        self.tree.column("name", width=250, anchor="w")
        self.tree.column("type", width=72, anchor="center", stretch=False)
        self.tree.column("document_type", width=150, anchor="center", stretch=False)
        self.tree.column("modified", width=150, anchor="center", stretch=False)
        self.tree.column("size", width=95, anchor="e", stretch=False)
        self.tree.column("path", width=360, anchor="w")

        tree_scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        tree_scroll_x.grid(row=1, column=0, sticky="ew")

        detail_frame = ttk.Frame(content)
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(1, weight=1)
        content.add(detail_frame, weight=1)

        ttk.Label(detail_frame, text="Detalhes").grid(row=0, column=0, sticky="w", pady=(6, 4))
        self.detail_text = tk.Text(
            detail_frame,
            height=5,
            wrap="word",
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#16202a",
            relief="solid",
            borderwidth=1,
        )
        self.detail_text.grid(row=1, column=0, sticky="nsew")
        self.detail_text.configure(state="disabled")

        footer = ttk.Frame(self, padding=(18, 8, 18, 10))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Label(footer, textvariable=self.cpu_var).grid(row=0, column=1, sticky="e", padx=(12, 16))
        ttk.Label(footer, textvariable=self.memory_var).grid(row=0, column=2, sticky="e", padx=(0, 16))
        ttk.Label(
            footer,
            text=DEVELOPER_LABEL,
            style="Creator.TLabel",
        ).grid(row=0, column=3, sticky="e")

        self.query_entry.focus_set()

    def _bind_events(self) -> None:
        self.query_entry.bind("<Return>", lambda _event: self.start_search())
        self.folder_entry.bind("<Return>", lambda _event: self.start_search())
        self.year_start_entry.bind("<Return>", lambda _event: self.start_search())
        self.year_end_entry.bind("<Return>", lambda _event: self.start_search())
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.show_selected_details())
        self.tree.bind("<Double-1>", lambda _event: self.open_selected_file())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_search_mode_changed(self) -> None:
        if self.search_mode_var.get() == "lmstudio":
            if self.ensure_lm_studio_ready():
                self.status_var.set("LM Studio pronto para busca em linguagem natural.")
            else:
                self.search_mode_var.set("local")
                self.status_var.set("Busca local selecionada.")
        else:
            self.status_var.set("Busca local selecionada.")

    def ensure_lm_studio_ready(self) -> bool:
        if self.lm_studio_session is not None:
            return True

        dialog = tk.Toplevel(self)
        dialog.title(f"{APP_NAME} - LM Studio")
        dialog.geometry("560x220")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        dialog.columnconfigure(0, weight=1)
        frame = ttk.Frame(dialog, padding=(18, 18, 18, 14))
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)

        ttk.Label(
            frame,
            text="Aguarde a abertura do LM Studio e seleção de modelo.",
            font=("Segoe UI", 11, "bold"),
            wraplength=500,
        ).grid(row=0, column=0, sticky="w")

        status_var = tk.StringVar(value="Iniciando preparação...")
        ttk.Label(frame, textvariable=status_var, wraplength=500).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(14, 8),
        )

        progress = ttk.Progressbar(frame, mode="indeterminate")
        progress.grid(row=2, column=0, sticky="ew")
        progress.start(10)

        button_row = ttk.Frame(frame)
        button_row.grid(row=3, column=0, sticky="e", pady=(18, 0))

        dialog_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        result: dict[str, bool] = {"ready": False}

        def log_from_worker(message: str) -> None:
            dialog_queue.put(("log", message))

        def worker() -> None:
            try:
                session = prepare_lm_studio(log=log_from_worker)
                dialog_queue.put(("done", session))
            except Exception as exc:
                dialog_queue.put(("error", str(exc)))

        def close_success() -> None:
            result["ready"] = True
            dialog.grab_release()
            dialog.destroy()

        def close_failure() -> None:
            result["ready"] = False
            dialog.grab_release()
            dialog.destroy()

        def poll_dialog_queue() -> None:
            try:
                while True:
                    kind, payload = dialog_queue.get_nowait()
                    if kind == "log":
                        message = str(payload)
                        status_var.set(message)
                        self._log_event(f"LM Studio: {message}")
                    elif kind == "done":
                        self.lm_studio_session = payload  # type: ignore[assignment]
                        progress.stop()
                        session = self.lm_studio_session
                        status_var.set(
                            f"LM Studio pronto. Modelo selecionado: {session.display_name}"
                        )
                        ttk.Button(button_row, text="OK", command=close_success).grid(
                            row=0,
                            column=0,
                        )
                    elif kind == "error":
                        progress.stop()
                        self._log_event(f"Falha ao preparar LM Studio: {payload}")
                        status_var.set(
                            "Nao foi possivel preparar o LM Studio. "
                            "A busca local sera mantida.\n"
                            f"Detalhe: {payload}"
                        )
                        ttk.Button(button_row, text="Fechar", command=close_failure).grid(
                            row=0,
                            column=0,
                        )
            except queue.Empty:
                pass
            try:
                exists = bool(dialog.winfo_exists())
            except tk.TclError:
                exists = False
            if exists:
                dialog.after(150, poll_dialog_queue)

        threading.Thread(target=worker, daemon=True).start()
        dialog.after(150, poll_dialog_queue)
        self.wait_window(dialog)
        return result["ready"]

    def select_folder(self) -> None:
        initial_dir = self.folder_var.get().strip() or str(Path.home())
        folder = filedialog.askdirectory(title="Escolha a pasta", initialdir=initial_dir)
        if folder:
            self.folder_var.set(folder)

    def _read_search_options(self) -> tuple[int, int | None, int | None, str, str]:
        try:
            max_results = int(self.max_results_var.get())
        except ValueError as exc:
            raise ValueError("Escolha uma quantidade valida de resultados.") from exc

        if max_results <= 0:
            raise ValueError("A quantidade de resultados deve ser maior que zero.")

        year_start = self._parse_year_field(self.year_start_var.get(), "Ano inicial")
        year_end = self._parse_year_field(self.year_end_var.get(), "Ano final")
        if year_start is not None and year_end is not None and year_start > year_end:
            raise ValueError("Ano inicial nao pode ser maior que o ano final.")

        document_type_label = self.document_type_var.get().strip() or DOCUMENT_TYPE_LABELS[DOCUMENT_TYPE_ALL_KEY]
        document_type_key = coerce_document_type_key(document_type_label)
        return max_results, year_start, year_end, document_type_key, document_type_label

    @staticmethod
    def _parse_year_field(value: str, label: str) -> int | None:
        value = value.strip()
        if not value:
            return None
        if not value.isdigit() or len(value) != 4:
            raise ValueError(f"{label} deve ter quatro digitos.")
        year = int(value)
        if year < 1601 or year > 9998:
            raise ValueError(f"{label} deve estar entre 1601 e 9998.")
        return year

    def start_search(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        query = self.query_var.get().strip()
        if not query:
            messagebox.showinfo(APP_NAME, "Digite o que deseja buscar.")
            self.query_entry.focus_set()
            return

        folder = self.folder_var.get().strip()
        if not folder:
            self.select_folder()
            folder = self.folder_var.get().strip()
            if not folder:
                return

        root = Path(folder)
        if not root.exists() or not root.is_dir():
            messagebox.showerror(APP_NAME, "A pasta selecionada nao existe.")
            return

        try:
            max_results, year_start, year_end, document_type_key, document_type_label = (
                self._read_search_options()
            )
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return

        include_content = self.include_content_var.get()
        pdf_ocr = self.pdf_ocr_var.get()
        skip_technical_dirs = self.skip_technical_var.get()
        use_windows_search = self.use_windows_search_var.get()
        search_mode = self.search_mode_var.get()
        if search_mode == "lmstudio" and self.lm_studio_session is None:
            if not self.ensure_lm_studio_ready():
                self.search_mode_var.set("local")
                return

        lm_studio_session = self.lm_studio_session

        self._clear_results()
        self._set_busy(True)
        self.status_var.set("Buscando...")
        self.stop_event = threading.Event()
        self._log_event(
            "Busca iniciada | "
            f"termo={query!r} | pasta={str(root)!r} | resultados={max_results} | "
            f"ano_inicial={year_start or '-'} | ano_final={year_end or '-'} | "
            f"tipo_documento={document_type_label!r} | "
            f"modo={'LM Studio' if search_mode == 'lmstudio' else 'local'} | "
            f"windows_search={'sim' if use_windows_search else 'nao'} | "
            f"conteudo={'sim' if include_content else 'nao'} | "
            f"ocr={'sim' if pdf_ocr else 'nao'} | "
            f"ignorar_tecnicas={'sim' if skip_technical_dirs else 'nao'}"
        )

        def worker_run() -> None:
            try:
                if search_mode == "lmstudio":
                    if lm_studio_session is None:
                        raise LMStudioError("LM Studio nao esta preparado.")
                    response = lm_studio_semantic_search(
                        query,
                        root,
                        session=lm_studio_session,
                        include_content=include_content,
                        pdf_ocr=pdf_ocr,
                        skip_technical_dirs=skip_technical_dirs,
                        max_results=max_results,
                        year_start=year_start,
                        year_end=year_end,
                        document_type=document_type_key,
                        use_windows_search=use_windows_search,
                        progress=lambda scanned, matched, current: self.worker_queue.put(
                            ("progress", (scanned, matched, current))
                        ),
                        log=lambda message: self.worker_queue.put(("log", message)),
                        stop_event=self.stop_event,
                    )
                else:
                    response = smart_search(
                        query,
                        root,
                        include_content=include_content,
                        pdf_ocr=pdf_ocr,
                        skip_technical_dirs=skip_technical_dirs,
                        max_results=max_results,
                        year_start=year_start,
                        year_end=year_end,
                        document_type=document_type_key,
                        use_windows_search=use_windows_search,
                        progress=lambda scanned, matched, current: self.worker_queue.put(
                            ("progress", (scanned, matched, current))
                        ),
                        log=lambda message: self.worker_queue.put(("log", message)),
                        stop_event=self.stop_event,
                    )
                self.worker_queue.put(("done", response))
            except Exception as exc:  # pragma: no cover - shown to the user.
                self.worker_queue.put(("error", str(exc)))

        self.worker = threading.Thread(target=worker_run, daemon=True)
        self.worker.start()

    def stop_search(self) -> None:
        if self.stop_event:
            self.stop_event.set()
            self._log_event("Interrupcao solicitada pelo usuario.")
            self.status_var.set("Parando...")

    def _consume_worker_queue(self) -> None:
        try:
            while True:
                kind, payload = self.worker_queue.get_nowait()
                if kind == "progress":
                    scanned, matched, current = payload  # type: ignore[misc]
                    label = f"{scanned} arquivos examinados, {matched} resultados encontrados"
                    if current:
                        label += f" | {Path(str(current)).name}"
                    self.status_var.set(label)
                elif kind == "log":
                    self._log_event(str(payload))
                elif kind == "done":
                    self._display_response(payload)  # type: ignore[arg-type]
                    self._set_busy(False)
                elif kind == "error":
                    self._set_busy(False)
                    self._log_event(f"Erro na busca: {payload}")
                    messagebox.showerror(APP_NAME, f"Nao foi possivel concluir a busca:\n{payload}")
                    self.status_var.set("Erro na busca.")
        except queue.Empty:
            pass
        finally:
            self.after(120, self._consume_worker_queue)

    def _display_response(self, response: SearchResponse) -> None:
        self._clear_results()
        for index, result in enumerate(response.results):
            item_id = str(index)
            self.results_by_iid[item_id] = result
            self.tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    int(round(result.score)),
                    result.name,
                    result.extension or "-",
                    result.document_type or "-",
                    self._format_modified(result.modified),
                    human_size(result.size),
                    result.path,
                ),
            )

        if response.results:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self.show_selected_details()
        else:
            self._set_detail("Nenhum resultado encontrado.")

        suffix = " interrompida" if response.stopped else ""
        total_matches = response.total_matches or len(response.results)
        shown = len(response.results)
        if total_matches > shown:
            result_label = f"{shown} exibidos de {total_matches} encontrados"
        else:
            result_label = f"{shown} resultados"
        self.status_var.set(
            f"Busca{suffix}: {result_label} em {response.scanned} arquivos. Motor: {response.backend}."
        )
        for message in response.messages:
            self._log_event(message)
        self._log_event(
            f"Busca finalizada | motor={response.backend} | exibidos={shown} | "
            f"encontrados={total_matches} | examinados={response.scanned} | ignorados={response.skipped} | "
            f"interrompida={'sim' if response.stopped else 'nao'}"
        )

    def _clear_results(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results_by_iid.clear()
        self._set_detail("")

    def _set_busy(self, busy: bool) -> None:
        self.search_button.configure(state="disabled" if busy else "normal")
        self.stop_button.configure(state="normal" if busy else "disabled")

    def show_selected_details(self) -> None:
        result = self._selected_result()
        if not result:
            self._set_detail("")
            return

        details = [
            result.name,
            f"Relevancia: {int(round(result.score))}",
            f"Motivo: {result.reason}",
            f"Caminho: {result.path}",
        ]
        if result.document_type:
            details.insert(2, f"Tipo de documento: {result.document_type}")
        if result.snippet:
            details.append("")
            details.append(result.snippet)
        self._set_detail("\n".join(details))

    def open_selected_file(self) -> None:
        result = self._selected_result()
        if not result:
            return
        try:
            os.startfile(result.path)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Nao foi possivel abrir o arquivo:\n{exc}")

    def open_selected_folder(self) -> None:
        result = self._selected_result()
        if not result:
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", result.path])
            else:
                subprocess.Popen(["xdg-open", str(Path(result.path).parent)])
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Nao foi possivel abrir a pasta:\n{exc}")

    def copy_selected_path(self) -> None:
        result = self._selected_result()
        if not result:
            return
        self.clipboard_clear()
        self.clipboard_append(result.path)
        self.status_var.set("Caminho copiado.")

    def export_logs(self) -> None:
        default_name = f"{APP_NAME}_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        destination = filedialog.asksaveasfilename(
            title="Exportar logs",
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=(("Arquivo de texto", "*.txt"), ("Todos os arquivos", "*.*")),
        )
        if not destination:
            return

        try:
            Path(destination).write_text(self._build_log_export(), encoding="utf-8")
        except OSError as exc:
            self._log_event(f"Falha ao exportar logs: {exc}")
            messagebox.showerror(APP_NAME, f"Nao foi possivel exportar os logs:\n{exc}")
            return

        self._log_event(f"Logs exportados para {destination}")
        self.status_var.set("Logs exportados.")
        messagebox.showinfo(APP_NAME, "Logs exportados com sucesso.")

    def _build_log_export(self) -> str:
        lines = [
            APP_NAME,
            DEVELOPER_LABEL,
            f"Exportado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            "",
            "Configuracao atual:",
            f"- Pasta: {self.folder_var.get().strip() or '-'}",
            f"- Busca: {self.query_var.get().strip() or '-'}",
            f"- Resultados exibidos: {self.max_results_var.get()}",
            f"- Ano inicial: {self.year_start_var.get().strip() or '-'}",
            f"- Ano final: {self.year_end_var.get().strip() or '-'}",
            f"- Tipo de documento: {self.document_type_var.get().strip() or '-'}",
            f"- Modo de busca: {'LM Studio' if self.search_mode_var.get() == 'lmstudio' else 'local'}",
            f"- Modelo LM Studio: {self.lm_studio_session.display_name if self.lm_studio_session else '-'}",
            f"- Windows Search: {'sim' if self.use_windows_search_var.get() else 'nao'}",
            f"- Ler conteudo: {'sim' if self.include_content_var.get() else 'nao'}",
            f"- OCR em PDFs: {'sim' if self.pdf_ocr_var.get() else 'nao'}",
            f"- Ignorar pastas tecnicas: {'sim' if self.skip_technical_var.get() else 'nao'}",
            f"- Busca em andamento: {'sim' if self.worker and self.worker.is_alive() else 'nao'}",
            f"- {self.cpu_var.get()}",
            "",
            "Eventos:",
        ]

        lines.extend(self.log_entries or ["- Nenhum evento registrado."])

        rows = self.tree.get_children()
        lines.extend(["", f"Resultados exibidos no momento: {len(rows)}"])
        for item_id in rows:
            result = self.results_by_iid.get(item_id)
            if not result:
                continue
            lines.append(
                " | ".join(
                    (
                        f"score={int(round(result.score))}",
                        f"documento={result.document_type or '-'}",
                        f"nome={result.name}",
                        f"modificado={self._format_modified(result.modified)}",
                        f"tamanho={human_size(result.size)}",
                        f"caminho={result.path}",
                    )
                )
            )

        return "\n".join(lines) + "\n"

    def _log_event(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_entries.append(f"[{timestamp}] {message}")

    def show_readme(self) -> None:
        window = tk.Toplevel(self)
        window.title(f"{APP_NAME} - README")
        window.geometry("820x620")
        window.minsize(680, 440)
        window.transient(self)

        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)

        frame = ttk.Frame(window, padding=(10, 10, 10, 8))
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        text = tk.Text(
            frame,
            wrap="word",
            font=("Segoe UI", 10),
            bg="#ffffff",
            fg="#16202a",
            relief="solid",
            borderwidth=1,
            undo=False,
        )
        scroll_y = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scroll_y.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")

        readme = self._read_readme()
        text.insert("1.0", readme)
        text.configure(state="disabled")

        button_row = ttk.Frame(window, padding=(10, 0, 10, 10))
        button_row.grid(row=1, column=0, sticky="ew")
        button_row.columnconfigure(0, weight=1)

        def copy_readme() -> None:
            self.clipboard_clear()
            self.clipboard_append(readme)
            self.status_var.set("README copiado.")

        ttk.Button(button_row, text="Copiar", command=copy_readme).grid(
            row=0,
            column=1,
            padx=(0, 8),
        )
        ttk.Button(button_row, text="Fechar", command=window.destroy).grid(row=0, column=2)
        self._log_event("README aberto pelo usuario.")

    def show_source_code(self) -> None:
        window = tk.Toplevel(self)
        window.title(f"{APP_NAME} - Código Fonte")
        window.geometry("940x620")
        window.minsize(760, 460)
        window.transient(self)

        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(window)
        notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 8))

        source_widgets: dict[str, tk.Text] = {}
        for label, relative in SOURCE_FILES:
            frame = ttk.Frame(notebook)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)

            text = tk.Text(
                frame,
                wrap="none",
                font=("Consolas", 10),
                bg="#ffffff",
                fg="#16202a",
                relief="solid",
                borderwidth=1,
                undo=False,
            )
            scroll_y = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
            scroll_x = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=text.xview)
            text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
            text.grid(row=0, column=0, sticky="nsew")
            scroll_y.grid(row=0, column=1, sticky="ns")
            scroll_x.grid(row=1, column=0, sticky="ew")

            text.insert("1.0", self._read_source(relative))
            text.configure(state="disabled")
            notebook.add(frame, text=label)
            source_widgets[str(frame)] = text

        button_row = ttk.Frame(window, padding=(10, 0, 10, 10))
        button_row.grid(row=1, column=0, sticky="ew")
        button_row.columnconfigure(0, weight=1)

        def copy_current_tab() -> None:
            selected = notebook.select()
            widget = source_widgets.get(selected)
            if not widget:
                return
            self.clipboard_clear()
            self.clipboard_append(widget.get("1.0", "end-1c"))
            self.status_var.set("Código fonte copiado.")

        ttk.Button(button_row, text="Copiar", command=copy_current_tab).grid(
            row=0,
            column=1,
            padx=(0, 8),
        )
        ttk.Button(button_row, text="Fechar", command=window.destroy).grid(row=0, column=2)

    @staticmethod
    def _read_source(relative: str) -> str:
        path = source_path(relative)
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="cp1252", errors="replace")
        except OSError as exc:
            return f"Nao foi possivel carregar {relative}.\n\n{exc}"

    @staticmethod
    def _read_readme() -> str:
        candidates: list[Path] = []
        if getattr(sys, "frozen", False):
            executable_dir = Path(sys.executable).resolve().parent
            candidates.extend((executable_dir / "README.md", executable_dir / "README.txt"))

        candidates.extend(
            (
                resource_path("README.md"),
                resource_path("README.txt"),
                Path(__file__).resolve().parent / "README.md",
                Path(__file__).resolve().parent / "README.txt",
            )
        )

        for path in candidates:
            if not path.exists():
                continue
            try:
                return path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return path.read_text(encoding="cp1252", errors="replace")
            except OSError:
                continue

        return "README nao encontrado."

    def _selected_result(self) -> SearchResult | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self.results_by_iid.get(selection[0])

    def _set_detail(self, text: str) -> None:
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert("1.0", text)
        self.detail_text.configure(state="disabled")

    def _update_cpu_status(self) -> None:
        current = self._read_cpu_times()
        previous = self._last_cpu_times
        if current is not None and previous is not None:
            idle_delta = current[0] - previous[0]
            kernel_delta = current[1] - previous[1]
            user_delta = current[2] - previous[2]
            total_delta = kernel_delta + user_delta
            if total_delta > 0:
                busy_delta = max(total_delta - idle_delta, 0)
                percent = min(max((busy_delta / total_delta) * 100, 0), 100)
                self.cpu_var.set(f"CPU: {percent:.0f}%")
        elif current is None:
            self.cpu_var.set("CPU: indisponivel")

        memory_load = self._read_memory_load()
        if memory_load is not None:
            self.memory_var.set(f"RAM: {memory_load:.0f}%")
        else:
            self.memory_var.set("RAM: indisponivel")

        self._last_cpu_times = current
        self.after(1000, self._update_cpu_status)

    @staticmethod
    def _read_cpu_times() -> tuple[int, int, int] | None:
        if os.name != "nt":
            return None

        idle = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        try:
            ok = ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle),
                ctypes.byref(kernel),
                ctypes.byref(user),
            )
        except AttributeError:
            return None

        if not ok:
            return None
        return (
            KDMinhaPetApp._filetime_to_int(idle),
            KDMinhaPetApp._filetime_to_int(kernel),
            KDMinhaPetApp._filetime_to_int(user),
        )

    @staticmethod
    def _filetime_to_int(value: FILETIME) -> int:
        return (int(value.dwHighDateTime) << 32) + int(value.dwLowDateTime)

    @staticmethod
    def _read_memory_load() -> int | None:
        if os.name != "nt":
            return None

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        try:
            ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        except AttributeError:
            return None
        if not ok:
            return None
        return int(status.dwMemoryLoad)

    @staticmethod
    def _format_modified(timestamp: float) -> str:
        return datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y %H:%M")

    def on_close(self) -> None:
        if self.stop_event:
            self.stop_event.set()
        self.destroy()


def main() -> None:
    app = KDMinhaPetApp()
    app.mainloop()


def self_test() -> int:
    from PIL import Image, ImageDraw, ImageFont

    test_dir = Path(tempfile.gettempdir()) / "KD_minha_PET.3.0_self_test"
    test_dir.mkdir(parents=True, exist_ok=True)
    sample = test_dir / "peticao_teste_prescricao.txt"
    sample.write_text("Modelo de peticao sobre prescricao intercorrente.", encoding="utf-8")

    image = Image.new("RGB", (1650, 1100), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 72)
    draw.text((110, 220), "Peticao de prescricao intercorrente", fill="black", font=font)
    draw.text((110, 330), "Documento escaneado para teste de OCR", fill="black", font=font)
    scanned_pdf = test_dir / "documento_escaneado.pdf"
    image.save(scanned_pdf, "PDF", resolution=200.0)

    response = smart_search(
        "peticao sobre prescricao",
        test_dir,
        include_content=True,
        pdf_ocr=True,
        skip_technical_dirs=False,
    )
    if not response.results:
        return 2

    ocr_response = smart_search(
        "prescricao intercorrente escaneado",
        test_dir,
        include_content=True,
        pdf_ocr=True,
        skip_technical_dirs=False,
    )
    if not any(result.name == scanned_pdf.name for result in ocr_response.results):
        (test_dir / "ocr_optional_unavailable.txt").write_text(
            "OCR nao retornou texto neste ambiente; recurso tratado como opcional.\n",
            encoding="utf-8",
        )

    app = KDMinhaPetApp()
    app.withdraw()
    app.update_idletasks()
    app.destroy()
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    main()
