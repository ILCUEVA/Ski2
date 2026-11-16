#Requires -Version 5.1
# Crea el entorno virtual (si no existe), instala dependencias y levanta Balancea.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Creando entorno virtual (.venv)..."
    py -3 -m venv .venv
}

Write-Host "Instalando dependencias..."
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "Iniciando Balancea en http://127.0.0.1:5000 ..."
.\.venv\Scripts\python.exe app.py
