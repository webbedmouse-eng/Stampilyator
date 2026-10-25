# Сборка лёгкого загрузчика Штампилятора.
# Требуется только .NET Framework 4.8 (csc.exe входит в Windows).
# Запуск: .\build_launcher.ps1

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$version = "1.3.1"
$appZip = Join-Path $PSScriptRoot "dist\Штампилятор-$version-win64.zip"
$runtimeZip = Join-Path $PSScriptRoot "dist\runtime-$version.zip"
$source = Join-Path $PSScriptRoot "launcher\Launcher.cs"
$output = Join-Path $PSScriptRoot "dist\Штампилятор-$version-bootstrap.exe"
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$icon = Join-Path $PSScriptRoot "assets\app.ico"

if (-not (Test-Path -LiteralPath $appZip)) {
    throw "Сначала соберите приложение: dist\Штампилятор-$version-win64.zip не найден."
}
if (-not (Test-Path -LiteralPath $csc)) {
    throw "Не найден csc.exe (.NET Framework 4.8)."
}

Copy-Item -LiteralPath $appZip -Destination $runtimeZip -Force
$hash = (Get-FileHash -LiteralPath $runtimeZip -Algorithm SHA256).Hash.ToLowerInvariant()
$content = Get-Content -LiteralPath $source -Raw -Encoding UTF8
$updated = [regex]::Replace(
    $content,
    'DefaultSha256\s*=\s*"[0-9a-fA-F]+"',
    'DefaultSha256 =' + [Environment]::NewLine + '            "' + $hash + '"'
)
if ($updated -ne $content) {
    Set-Content -LiteralPath $source -Value $updated -Encoding UTF8 -NoNewline
}

& $csc /nologo /target:winexe /optimize+ /platform:anycpu `
    "/out:$output" "/win32icon:$icon" `
    /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll `
    /reference:System.Windows.Forms.dll /reference:System.Net.Http.dll `
    /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll `
    (Join-Path $PSScriptRoot "launcher\Launcher.cs")
if ($LASTEXITCODE -ne 0) {
    throw "Компиляция загрузчика завершилась с ошибкой."
}

$size = (Get-Item -LiteralPath $output).Length
if ($size -gt 8MB) {
    throw "Загрузчик получился больше 8 МБ: $size байт."
}
Set-Content -LiteralPath (Join-Path $PSScriptRoot "dist\runtime-$version.sha256") -Value $hash -Encoding ASCII
$runtimeMb = [math]::Round((Get-Item -LiteralPath $runtimeZip).Length / 1MB, 1)
$loaderKb = [math]::Round($size / 1KB, 1)
Write-Host ""
Write-Host "Готово: $output" -ForegroundColor Green
Write-Host "Загрузчик: $loaderKb КБ; runtime-архив: $runtimeMb МБ; SHA-256: $hash" -ForegroundColor Green
