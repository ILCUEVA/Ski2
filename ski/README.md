# Balancea

Aplicación web local (Flask + SQLite) para clasificar balances y generar
estados de resultados bajo NIIF 18.

## Requisitos
- Python 3.11 o superior instalado y disponible en el PATH.

## Cómo levantar el servicio

### Windows (PowerShell)
```powershell
.\run.ps1
```

### Linux / macOS
```bash
chmod +x run.sh   # solo la primera vez
./run.sh
```

Estos scripts crean el entorno virtual `.venv` (si no existe), instalan las
dependencias de `requirements.txt` y levantan el servidor.

### Pasos manuales (alternativa)
```bash
python -m venv .venv
# Windows: .venv\Scripts\python.exe -m pip install -r requirements.txt
# Linux/macOS: ./.venv/bin/python -m pip install -r requirements.txt
python app.py
```

Luego abre [http://127.0.0.1:5000](http://127.0.0.1:5000) en el navegador.
Para detener el servidor, presiona `Ctrl+C` en la terminal.

## Usuario demo
La primera vez que se levanta el servicio se siembran datos de ejemplo:
- Correo: `demo@balancea.com`
- Contraseña: `Balancea2026`

## Datos y configuración
- La base de datos (`instance/balancea.db`) y los informes generados
  (`instance/informes/`) se crean automáticamente al iniciar; no requieren
  configuración previa. Para reiniciar los datos desde cero, borra la carpeta
  `instance/` y vuelve a levantar el servicio.
- Variables de entorno opcionales:
  - `SECRET_KEY`: clave de sesión de Flask (recomendado definirla si se
    comparte el servicio más allá de uso local).
  - `HOST` (por defecto `127.0.0.1`), `PORT` (por defecto `5000`).
  - `FLASK_DEBUG` (`1` por defecto, usar `0` para desactivar el modo debug).
