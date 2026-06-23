$ErrorActionPreference = "Stop"

$InstallerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $InstallerDir
$BuildTools = "S:\Backup da Pasta Trabalho\Resumator 5.1 - Enhanced\build-tools"
$DistDir = Join-Path $ProjectDir "dist"
$AppDir = Join-Path $DistDir "KD_minha_PET.3.0"
$PayloadDir = Join-Path $InstallerDir "payload"
$PayloadZip = Join-Path $PayloadDir "KDMinhaPET30-app.zip"
$SetupSpec = Join-Path $ProjectDir "build-spec\KD_minha_PET Setup.spec"
$BuildDir = Join-Path $ProjectDir "build-setup"
$PreferredPython = "C:\Users\Leonardo\AppData\Local\Programs\Python\Python314\python.exe"
$PythonExe = if (Test-Path $PreferredPython) { $PreferredPython } else { "python" }

if (-not (Test-Path (Join-Path $AppDir "KD_minha_PET.3.0.exe"))) {
    throw "Aplicativo nao encontrado em $AppDir. Gere o app principal antes do instalador."
}

if (-not (Test-Path $BuildTools)) {
    throw "Nao encontrei as ferramentas locais de empacotamento: $BuildTools"
}

New-Item -ItemType Directory -Force -Path $PayloadDir | Out-Null
Compress-Archive -Path (Join-Path $AppDir "*") -DestinationPath $PayloadZip -Force
Copy-Item -LiteralPath (Join-Path $ProjectDir "README.txt") -Destination $PayloadDir -Force

$env:PYTHONPATH = "$ProjectDir;$BuildTools;$env:PYTHONPATH"
$env:PATH = "$BuildTools\bin;$env:PATH"

Push-Location $ProjectDir
try {
    & $PythonExe -m PyInstaller --noconfirm --clean --distpath $DistDir --workpath $BuildDir $SetupSpec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller falhou ao gerar o instalador."
    }
}
finally {
    Pop-Location
}

$SetupExe = Join-Path $DistDir "KD_minha_PET.3.0 Setup.exe"
if (-not (Test-Path $SetupExe)) {
    throw "Instalador nao gerado em $SetupExe"
}

Write-Host "Instalador criado: $SetupExe"
