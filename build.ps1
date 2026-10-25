# Сборка Windows-приложения Штампилятор.
# Запуск:  .\build.cmd   (или .\build.ps1)
# Параметры:
#   -SkipTests  не запускать тесты перед сборкой
#   -KeepBuild  не удалять каталог build

param(
    [switch]$SkipTests,
    [switch]$KeepBuild
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = "python"
$tempDir = Join-Path $PSScriptRoot ".tmp"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
# PyInstaller и pip пишут во временные каталоги; используем локальный.
$env:TMP = $tempDir
$env:TEMP = $tempDir

Write-Host "== Проверка зависимостей ==" -ForegroundColor Cyan
& $python -c "import PySide6, fitz, numpy, PIL, PyInstaller; print('PySide6', PySide6.__version__); print('PyMuPDF', fitz.__version__); print('PyInstaller', PyInstaller.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "Зависимости не установлены. Выполните: python -m pip install -r requirements.txt"
}

if (-not $SkipTests) {
    Write-Host "== Тесты ==" -ForegroundColor Cyan
    & $python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Тесты не пройдены — сборка остановлена."
    }
}

Write-Host "== Очистка ==" -ForegroundColor Cyan
if (Test-Path -LiteralPath "dist") {
    # Удаляем содержимое, а не сам каталог: на некоторых системах
    # корень dist может быть временно занят антивирусом или проводником.
    Get-ChildItem -LiteralPath "dist" -Force | Remove-Item -Recurse -Force
}
if (-not $KeepBuild -and (Test-Path -LiteralPath "build")) {
    Remove-Item -LiteralPath "build" -Recurse -Force
}

Write-Host "== PyInstaller ==" -ForegroundColor Cyan
& $python -m PyInstaller --noconfirm --clean Shtampilyator.spec
if ($LASTEXITCODE -ne 0) {
    throw "Сборка PyInstaller завершилась с ошибкой."
}

$appDir = Join-Path $PSScriptRoot "dist\Штампилятор"
$exe = Join-Path $appDir "Штампилятор.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Не найден результат сборки: $exe"
}

Write-Host "== Лицензии и исходный код ==" -ForegroundColor Cyan
$version = "1.3.1"
$sourceName = "Штампилятор-$version-source.zip"
foreach ($name in @("LICENSE", "THIRD_PARTY_NOTICES.md", "SOURCE.txt")) {
    $src = Join-Path $PSScriptRoot $name
    if (-not (Test-Path -LiteralPath $src)) {
        throw "Не найден обязательный файл: $src"
    }
    Copy-Item -LiteralPath $src -Destination $appDir -Force
}
$appLicenses = Join-Path $appDir "licenses"
if (Test-Path -LiteralPath $appLicenses) {
    Remove-Item -LiteralPath $appLicenses -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "licenses") -Destination $appDir -Recurse -Force

$sourceStage = Join-Path $tempDir "source"
if (Test-Path -LiteralPath $sourceStage) {
    Remove-Item -LiteralPath $sourceStage -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $sourceStage | Out-Null
foreach ($name in @(
    ".gitignore",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "SOURCE.txt",
    "README.md",
    "main.py",
    "requirements.txt",
    "build.ps1",
    "build.cmd",
    "Shtampilyator.spec",
    "version_info.txt"
)) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $sourceStage -Force
}
foreach ($name in @("pdfstamp", "assets", "tools", "docs", "licenses")) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $sourceStage -Recurse -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $sourceStage "tests") | Out-Null
Copy-Item -Path (Join-Path $PSScriptRoot "tests\*.py") -Destination (Join-Path $sourceStage "tests") -Force
Get-ChildItem -LiteralPath $sourceStage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

$sourceZip = Join-Path $appDir $sourceName
if (Test-Path -LiteralPath $sourceZip) {
    Remove-Item -LiteralPath $sourceZip -Force
}
Compress-Archive -Path (Join-Path $sourceStage "*") -DestinationPath $sourceZip -CompressionLevel Optimal
if (-not (Test-Path -LiteralPath $sourceZip)) {
    throw "Не удалось создать архив исходников: $sourceZip"
}

Write-Host "== ZIP ==" -ForegroundColor Cyan
$zip = Join-Path $PSScriptRoot "dist\Штампилятор-$version-win64.zip"
if (Test-Path -LiteralPath $zip) {
    Remove-Item -LiteralPath $zip -Force
}
Compress-Archive -LiteralPath $appDir -DestinationPath $zip -CompressionLevel Optimal

$dirMb = [math]::Round(((Get-ChildItem -LiteralPath $appDir -Recurse -File | Measure-Object Length -Sum).Sum) / 1MB, 1)
$zipMb = [math]::Round((Get-Item -LiteralPath $zip).Length / 1MB, 1)
Write-Host ""
Write-Host "Готово: $exe" -ForegroundColor Green
$sourceMb = [math]::Round((Get-Item -LiteralPath $sourceZip).Length / 1MB, 1)
Write-Host "Размер папки: $dirMb МБ; архив: $zip ($zipMb МБ); исходники: $sourceName ($sourceMb МБ)" -ForegroundColor Green
