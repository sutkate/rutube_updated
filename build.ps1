# build_without_c_drive.ps1
param(
    [string]$ScriptPath = "main.py",
    [string]$DriveLetter = "D",
    [string]$OutputName = "app.exe"
)

# Создаем директории на другом диске
$tempDir = "$DriveLetter`:\src\build\Temp\NuitkaBuild"
$cacheDir = "$DriveLetter`:\src\build\Cache\Nuitka"
$buildDir = "$DriveLetter`:\src\build\Build"

# Создаем директории если их нет
New-Item -ItemType Directory -Force -Path $tempDir
New-Item -ItemType Directory -Force -Path $cacheDir
New-Item -ItemType Directory -Force -Path $buildDir

# Устанавливаем переменные окружения
$env:TEMP = $tempDir
$env:TMP = $tempDir
$env:TMPDIR = $tempDir
$env:NUITKA_CACHE_DIR = $cacheDir
$env:SCONS_CACHE = $cacheDir

Write-Host "Временная директория: $tempDir" -ForegroundColor Yellow
Write-Host "Кэш Nuitka: $cacheDir" -ForegroundColor Yellow
Write-Host "Выходная директория: $buildDir" -ForegroundColor Yellow

# Очищаем предыдущие сборки
if (Test-Path "$buildDir\*") {
    Remove-Item -Path "$buildDir\*" -Recurse -Force
}

# Запускаем Nuitka с указанием всех путей
python -m nuitka `
  --onefile `
  --standalone `
  --follow-imports `
  --lto=no `
  --jobs=2 `
  --low-memory `
  --include-package=playwright `
  --include-package=aiohttp `
  --output-dir=$buildDir `
  --output-filename=$OutputName `
  --remove-output `
  --assume-yes-for-downloads `
  $ScriptPath

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Сборка успешно завершена!" -ForegroundColor Green
    Write-Host "📁 Исполняемый файл: $buildDir\$OutputName" -ForegroundColor Cyan
}