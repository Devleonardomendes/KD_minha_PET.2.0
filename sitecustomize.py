from __future__ import annotations

from pathlib import Path
import ctypes
import os
import sys


_TCL_DLL = None


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


def _initialize_tcl_runtime() -> None:
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


_initialize_tcl_runtime()
