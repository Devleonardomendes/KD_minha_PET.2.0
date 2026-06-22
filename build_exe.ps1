$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildTools = "S:\Backup da Pasta Trabalho\Resumator 5.1 - Enhanced\build-tools"
$LegacyTkRuntime = Join-Path $ProjectDir "dist\KD_minha_PET\_internal"
$IconPath = Join-Path $ProjectDir "assets\lupa.ico"
$OcrScriptPath = Join-Path $ProjectDir "tools\ocr_windows.ps1"
$AppPath = Join-Path $ProjectDir "app.py"
$SearchEnginePath = Join-Path $ProjectDir "search_engine.py"
$SitecustomizePath = Join-Path $ProjectDir "sitecustomize.py"
$BuildScriptPath = Join-Path $ProjectDir "build_exe.ps1"
$ShortcutScriptPath = Join-Path $ProjectDir "create_desktop_shortcut.ps1"
$InstallerScriptPath = Join-Path $ProjectDir "installer\setup_installer.py"
$ReadmePath = Join-Path $ProjectDir "README.txt"
$ReadmeMarkdownPath = Join-Path $ProjectDir "README.md"
$PreferredPython = "C:\Users\Leonardo\AppData\Local\Programs\Python\Python314\python.exe"
$PythonExe = if (Test-Path $PreferredPython) { $PreferredPython } else { "python" }
$PythonHome = Split-Path -Parent $PythonExe
$TkinterPackage = Join-Path $PythonHome "Lib\tkinter"

if (-not (Test-Path $IconPath)) {
    & $PythonExe (Join-Path $ProjectDir "tools\create_icon.py")
}

if (-not (Test-Path $BuildTools)) {
    throw "Nao encontrei as ferramentas locais de empacotamento: $BuildTools"
}

if (-not (Test-Path $LegacyTkRuntime)) {
    throw "Nao encontrei o runtime Tcl/Tk local ja validado: $LegacyTkRuntime"
}

if (-not (Test-Path $TkinterPackage)) {
    throw "Nao encontrei o pacote tkinter do Python local: $TkinterPackage"
}

$env:PYTHONPATH = "$ProjectDir;$BuildTools;$env:PYTHONPATH"
$env:PATH = "$BuildTools\bin;$env:PATH"

& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "KD_minha_PET.2.0" `
    --icon "$IconPath" `
    --add-data "$IconPath;assets" `
    --add-data "$OcrScriptPath;tools" `
    --add-data "$ReadmePath;." `
    --add-data "$ReadmeMarkdownPath;." `
    --add-data "$AppPath;source" `
    --add-data "$SearchEnginePath;source" `
    --add-data "$SitecustomizePath;source" `
    --add-data "$BuildScriptPath;source" `
    --add-data "$ShortcutScriptPath;source" `
    --add-data "$OcrScriptPath;source\tools" `
    --add-data "$InstallerScriptPath;source\installer" `
    --distpath (Join-Path $ProjectDir "dist") `
    --workpath (Join-Path $ProjectDir "build") `
    --specpath "$ProjectDir" `
    "$AppPath"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller falhou ao gerar o aplicativo."
}

$DistAppDir = Join-Path $ProjectDir "dist\KD_minha_PET.2.0"
$DistInternalDir = Join-Path $DistAppDir "_internal"
$TkRuntimeItems = @("_tcl_data", "_tk_data", "tcl8", "_tkinter.pyd", "tcl86t.dll", "tk86t.dll", "zlib1.dll")
foreach ($Item in $TkRuntimeItems) {
    $SourcePath = Join-Path $LegacyTkRuntime $Item
    $TargetPath = Join-Path $DistInternalDir $Item
    if (-not (Test-Path $SourcePath)) {
        throw "Componente Tcl/Tk ausente no runtime local: $SourcePath"
    }
    if ((Get-Item -LiteralPath $SourcePath).PSIsContainer) {
        New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null
        Copy-Item -Path (Join-Path $SourcePath "*") -Destination $TargetPath -Recurse -Force
    } else {
        Copy-Item -LiteralPath $SourcePath -Destination $TargetPath -Force
    }
}
$TkinterTarget = Join-Path $DistInternalDir "tkinter"
New-Item -ItemType Directory -Force -Path $TkinterTarget | Out-Null
Copy-Item -Path (Join-Path $TkinterPackage "*") -Destination $TkinterTarget -Recurse -Force

Copy-Item -LiteralPath $ReadmePath -Destination (Join-Path $DistAppDir "README.txt") -Force
if (Test-Path $ReadmeMarkdownPath) {
    Copy-Item -LiteralPath $ReadmeMarkdownPath -Destination (Join-Path $DistAppDir "README.md") -Force
}

$SourceDistDir = Join-Path $DistAppDir "source"
New-Item -ItemType Directory -Force -Path $SourceDistDir | Out-Null
$SourceFiles = @(
    @{ Source = $AppPath; Target = "app.py" },
    @{ Source = $SearchEnginePath; Target = "search_engine.py" },
    @{ Source = $SitecustomizePath; Target = "sitecustomize.py" },
    @{ Source = $BuildScriptPath; Target = "build_exe.ps1" },
    @{ Source = $ShortcutScriptPath; Target = "create_desktop_shortcut.ps1" },
    @{ Source = $OcrScriptPath; Target = "tools\ocr_windows.ps1" },
    @{ Source = $InstallerScriptPath; Target = "installer\setup_installer.py" }
)

foreach ($Item in $SourceFiles) {
    $SourcePath = $Item["Source"]
    $TargetPath = Join-Path $SourceDistDir $Item["Target"]
    if (Test-Path $SourcePath) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $TargetPath) | Out-Null
        Copy-Item -LiteralPath $SourcePath -Destination $TargetPath -Force
    }
}
