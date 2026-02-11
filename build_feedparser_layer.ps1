# -----------------------------
# Feedparser AWS Lambda Layer Builder
# -----------------------------

$ErrorActionPreference = "Stop"

$LayerName = "feedparser-layer"
$BuildDir  = "build"
$PythonDir = "$BuildDir\python"
$OutDir    = "dist"
$ZipPath   = "$OutDir\$LayerName.zip"

Write-Host "Cleaning old build..."
Remove-Item -Recurse -Force $BuildDir,$OutDir -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Path $PythonDir | Out-Null
New-Item -ItemType Directory -Path $OutDir    | Out-Null

Write-Host "Upgrading pip..."
python -m pip install --upgrade pip

Write-Host "Installing feedparser into layer folder..."
python -m pip install `
    --target $PythonDir `
    feedparser==6.0.11

Write-Host "Cleaning cache files..."
Get-ChildItem -Path $PythonDir -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Get-ChildItem -Path $PythonDir -Recurse -Include *.pyc,*.pyo -File |
    Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "Creating zip..."
Compress-Archive -Path "$BuildDir\python" -DestinationPath $ZipPath

Write-Host ""
Write-Host "✅ Layer created:"
Write-Host $ZipPath
