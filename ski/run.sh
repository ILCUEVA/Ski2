#!/usr/bin/env bash
# Crea el entorno virtual (si no existe), instala dependencias y levanta Balancea.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Creando entorno virtual (.venv)..."
    python3 -m venv .venv
fi

echo "Instalando dependencias..."
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt

echo "Iniciando Balancea en http://127.0.0.1:5000 ..."
./.venv/bin/python app.py
