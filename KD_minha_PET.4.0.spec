# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['S:\\PASTA DO CODEX\\Achei_minha_pet\\app.py'],
    pathex=[],
    binaries=[],
    datas=[('S:\\PASTA DO CODEX\\Achei_minha_pet\\assets\\lupa.ico', 'assets'), ('S:\\PASTA DO CODEX\\Achei_minha_pet\\tools\\ocr_windows.ps1', 'tools'), ('S:\\PASTA DO CODEX\\Achei_minha_pet\\README.txt', '.'), ('S:\\PASTA DO CODEX\\Achei_minha_pet\\README.md', '.'), ('S:\\PASTA DO CODEX\\Achei_minha_pet\\app.py', 'source'), ('S:\\PASTA DO CODEX\\Achei_minha_pet\\search_engine.py', 'source'), ('S:\\PASTA DO CODEX\\Achei_minha_pet\\lm_studio_integration.py', 'source'), ('S:\\PASTA DO CODEX\\Achei_minha_pet\\sitecustomize.py', 'source'), ('S:\\PASTA DO CODEX\\Achei_minha_pet\\build_exe.ps1', 'source'), ('S:\\PASTA DO CODEX\\Achei_minha_pet\\create_desktop_shortcut.ps1', 'source'), ('S:\\PASTA DO CODEX\\Achei_minha_pet\\tools\\ocr_windows.ps1', 'source\\tools'), ('S:\\PASTA DO CODEX\\Achei_minha_pet\\installer\\setup_installer.py', 'source\\installer')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KD_minha_PET.4.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['S:\\PASTA DO CODEX\\Achei_minha_pet\\assets\\lupa.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KD_minha_PET.4.0',
)
