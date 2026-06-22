$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ExePath = Join-Path $ProjectDir "dist\KD_minha_PET.2.0\KD_minha_PET.2.0.exe"
$FallbackLauncher = Join-Path $ProjectDir "run_KD_minha_PET.bat"
$IconPath = Join-Path $ProjectDir "assets\lupa.ico"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "KD_minha_PET.2.0.lnk"

if (Test-Path $ExePath) {
    $TargetPath = $ExePath
} elseif (Test-Path $FallbackLauncher) {
    $TargetPath = $FallbackLauncher
} else {
    throw "Nao encontrei o executavel nem o iniciador do aplicativo."
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.Description = "KD_minha_PET.2.0 - busca inteligente de arquivos"
if (Test-Path $IconPath) {
    $Shortcut.IconLocation = $IconPath
}
$Shortcut.Save()

Write-Output $ShortcutPath
