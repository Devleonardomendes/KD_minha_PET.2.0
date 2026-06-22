param(
    [Parameter(Mandatory = $true)]
    [string[]] $ImagePath
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.FileAccessMode, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime]

$script:AsTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object {
        $_.Name -eq "AsTask" -and
        $_.IsGenericMethodDefinition -and
        $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    } |
    Select-Object -First 1)

function Wait-WinRtOperation {
    param(
        [Parameter(Mandatory = $true)]
        $Operation,
        [Parameter(Mandatory = $true)]
        [type] $ResultType
    )

    $asTask = $script:AsTaskGeneric.MakeGenericMethod($ResultType)
    $task = $asTask.Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}

$engine = $null
try {
    $language = [Windows.Globalization.Language]::new("pt-BR")
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
} catch {
    $engine = $null
}

if ($null -eq $engine) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
}

if ($null -eq $engine) {
    throw "O OCR do Windows nao esta disponivel para os idiomas do usuario."
}

$items = New-Object System.Collections.Generic.List[object]

foreach ($path in $ImagePath) {
    $resolved = [System.IO.Path]::GetFullPath($path)
    $stream = $null
    try {
        $file = Wait-WinRtOperation `
            -Operation ([Windows.Storage.StorageFile]::GetFileFromPathAsync($resolved)) `
            -ResultType ([Windows.Storage.StorageFile])
        $stream = Wait-WinRtOperation `
            -Operation ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) `
            -ResultType ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Wait-WinRtOperation `
            -Operation ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) `
            -ResultType ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Wait-WinRtOperation `
            -Operation ($decoder.GetSoftwareBitmapAsync()) `
            -ResultType ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Wait-WinRtOperation `
            -Operation ($engine.RecognizeAsync($bitmap)) `
            -ResultType ([Windows.Media.Ocr.OcrResult])

        $items.Add([pscustomobject]@{
            path = $resolved
            text = $result.Text
            ok = $true
            error = $null
        }) | Out-Null
    } catch {
        $items.Add([pscustomobject]@{
            path = $resolved
            text = ""
            ok = $false
            error = $_.Exception.Message
        }) | Out-Null
    } finally {
        if ($null -ne $stream) {
            $stream.Dispose()
        }
    }
}

$items | ConvertTo-Json -Compress
