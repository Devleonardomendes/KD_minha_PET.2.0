from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
import winreg
import zipfile


APP_NAME = "KD_minha_PET.4.0"
APP_VERSION = "4.0"
PUBLISHER = "LEONARDO CARDOSO DE MELO TEIXEIRA MENDES"
INSTALLED_EXE = "KD_minha_PET.4.0.exe"
PAYLOAD_APP_ZIP = "KDMinhaPET40-app.zip"
PAYLOAD_README = "README.txt"
UNINSTALL_SCRIPT = "uninstall_kd_minha_pet_4_0.ps1"
UNINSTALL_REG_PATH = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"


def _resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    direct = base / name
    if direct.exists():
        return direct
    return base / "payload" / name


def _install_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Programs" / APP_NAME
    return Path.home() / APP_NAME


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _create_shortcuts(target: Path) -> None:
    target_text = _ps_quote(str(target))
    shortcut_name = _ps_quote(f"{APP_NAME}.lnk")
    description = _ps_quote("KD_minha_PET.4.0 - busca local de arquivos")
    command = (
        "$desktop=[Environment]::GetFolderPath('Desktop'); "
        "$programs=[Environment]::GetFolderPath('Programs'); "
        f"$target={target_text}; "
        f"$shortcutName={shortcut_name}; "
        f"$description={description}; "
        "$workdir=Split-Path -Parent $target; "
        "$shell=New-Object -ComObject WScript.Shell; "
        "$shortcut=$shell.CreateShortcut((Join-Path $desktop $shortcutName)); "
        "$shortcut.TargetPath=$target; "
        "$shortcut.WorkingDirectory=$workdir; "
        "$shortcut.Description=$description; "
        "$shortcut.IconLocation=$target; "
        "$shortcut.Save(); "
        "$shortcut=$shell.CreateShortcut((Join-Path $programs $shortcutName)); "
        "$shortcut.TargetPath=$target; "
        "$shortcut.WorkingDirectory=$workdir; "
        "$shortcut.Description=$description; "
        "$shortcut.IconLocation=$target; "
        "$shortcut.Save()"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=False,
        creationflags=creationflags,
    )


def _estimated_size_kb(path: Path) -> int:
    total = 0
    for file_path in path.rglob("*"):
        if not file_path.is_file():
            continue
        try:
            total += file_path.stat().st_size
        except OSError:
            pass
    return max(1, total // 1024)


def _create_uninstaller(destination_dir: Path) -> Path:
    uninstaller = destination_dir / UNINSTALL_SCRIPT
    cleanup_name = "kd-minha-pet-4.0-cleanup.cmd"
    script = f"""$ErrorActionPreference = 'SilentlyContinue'
$appName = {_ps_quote(APP_NAME)}
$installDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$exePath = Join-Path $installDir {_ps_quote(INSTALLED_EXE)}

Get-Process | Where-Object {{ $_.Path -eq $exePath }} | Stop-Process -Force

$desktop = [Environment]::GetFolderPath('Desktop')
$programs = [Environment]::GetFolderPath('Programs')
Remove-Item -LiteralPath (Join-Path $desktop ($appName + '.lnk')) -Force
Remove-Item -LiteralPath (Join-Path $programs ($appName + '.lnk')) -Force
Remove-Item -LiteralPath ('HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\' + $appName) -Recurse -Force

$cleanup = Join-Path $env:TEMP {_ps_quote(cleanup_name)}
$lines = @(
    '@echo off',
    'cd /d "%TEMP%"',
    'timeout /t 2 /nobreak >nul',
    'rmdir /s /q "' + $installDir + '"',
    'del "%~f0"'
)
Set-Content -LiteralPath $cleanup -Value $lines -Encoding ASCII
Start-Process -FilePath $env:ComSpec -ArgumentList @('/c', '"' + $cleanup + '"') -WorkingDirectory $env:TEMP -WindowStyle Hidden
"""
    try:
        uninstaller.write_text(script, encoding="utf-8")
    except OSError:
        if uninstaller.exists():
            return uninstaller
        raise
    return uninstaller


def _register_uninstall_entry(destination_dir: Path, target: Path, uninstaller: Path) -> None:
    uninstall_command = (
        f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{uninstaller}"'
    )
    values = {
        "DisplayName": (winreg.REG_SZ, APP_NAME),
        "DisplayVersion": (winreg.REG_SZ, APP_VERSION),
        "Publisher": (winreg.REG_SZ, PUBLISHER),
        "InstallLocation": (winreg.REG_SZ, str(destination_dir)),
        "DisplayIcon": (winreg.REG_SZ, f"{target},0"),
        "UninstallString": (winreg.REG_SZ, uninstall_command),
        "QuietUninstallString": (winreg.REG_SZ, uninstall_command),
        "InstallDate": (winreg.REG_SZ, datetime.now().strftime("%Y%m%d")),
        "EstimatedSize": (winreg.REG_DWORD, _estimated_size_kb(destination_dir)),
        "NoModify": (winreg.REG_DWORD, 1),
        "NoRepair": (winreg.REG_DWORD, 1),
    }
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH, 0, winreg.KEY_WRITE) as key:
            for name, (value_type, value) in values.items():
                winreg.SetValueEx(key, name, 0, value_type, value)
    except OSError:
        _register_uninstall_entry_reg_exe(values)
        return

    if not _uninstall_entry_exists():
        _register_uninstall_entry_reg_exe(values)


def _uninstall_entry_exists() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH, 0, winreg.KEY_READ):
            return True
    except OSError:
        return False


def _register_uninstall_entry_reg_exe(values: dict[str, tuple[int, str | int]]) -> None:
    key_path = rf"HKCU\{UNINSTALL_REG_PATH}"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for name, (value_type, value) in values.items():
        reg_type = "REG_DWORD" if value_type == winreg.REG_DWORD else "REG_SZ"
        subprocess.run(
            ["reg", "add", key_path, "/v", name, "/t", reg_type, "/d", str(value), "/f"],
            check=True,
            creationflags=creationflags,
        )


def main() -> int:
    source = _resource_path(PAYLOAD_APP_ZIP)
    readme_source = _resource_path(PAYLOAD_README)
    destination_dir = _install_dir()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / INSTALLED_EXE

    with zipfile.ZipFile(source) as archive:
        archive.extractall(destination_dir)

    if readme_source.exists():
        shutil.copy2(readme_source, destination_dir / PAYLOAD_README)

    _create_shortcuts(destination)
    uninstaller = _create_uninstaller(destination_dir)
    _register_uninstall_entry(destination_dir, destination, uninstaller)
    subprocess.Popen([str(destination)], cwd=str(destination_dir))
    return 0


def self_test() -> int:
    source = _resource_path(PAYLOAD_APP_ZIP)
    output_dir = Path(tempfile.gettempdir()) / "kd-minha-pet-4.0-setup-self-test"
    output_dir.mkdir(parents=True, exist_ok=True)
    diagnostic = output_dir / "diagnostic.txt"
    diagnostic.write_text(
        f"source={source}\nexists={source.exists()}\nsize={source.stat().st_size if source.exists() else 0}\n",
        encoding="utf-8",
    )
    if not source.exists() or source.stat().st_size <= 0:
        return 2

    with zipfile.ZipFile(source) as archive:
        names = set(archive.namelist())
        if INSTALLED_EXE not in names:
            diagnostic.write_text(f"missing={INSTALLED_EXE}\n", encoding="utf-8")
            return 3
        if not any(name.startswith("_internal/python") for name in names):
            diagnostic.write_text("missing=embedded_python\n", encoding="utf-8")
            return 4
        if "README.txt" not in names:
            diagnostic.write_text("missing=README.txt\n", encoding="utf-8")
            return 5
        if (
            "source/app.py" not in names
            or "source/search_engine.py" not in names
            or "source/lm_studio_integration.py" not in names
        ):
            diagnostic.write_text("missing=source_files\n", encoding="utf-8")
            return 6
        archive.extractall(output_dir / "app")

    shutil.copy2(source, output_dir / PAYLOAD_APP_ZIP)
    if readme_source := _resource_path(PAYLOAD_README):
        if readme_source.exists():
            shutil.copy2(readme_source, output_dir / PAYLOAD_README)
    (output_dir / "ok.txt").write_text("ok", encoding="utf-8")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    raise SystemExit(main())
