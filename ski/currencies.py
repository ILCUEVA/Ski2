"""Catálogo de monedas (ISO 4217) con un tipo de cambio fijo de referencia.

El tipo de cambio es fijo (no se actualiza contra una API externa) y se
expresa como "cuántos CLP equivalen a 1 unidad de esa moneda". Sirve para
presentar montos en distintas monedas de forma consistente dentro de la app.
Puede reemplazarse más adelante por una fuente de tasas en vivo.
"""

MONEDA_BASE = "CLP"

MONEDAS = [
    {"codigo": "CLP", "nombre": "Peso chileno", "tipo_cambio_clp": 1.0},
    {"codigo": "USD", "nombre": "Dólar estadounidense", "tipo_cambio_clp": 950.0},
    {"codigo": "EUR", "nombre": "Euro", "tipo_cambio_clp": 1030.0},
    {"codigo": "COP", "nombre": "Peso colombiano", "tipo_cambio_clp": 0.23},
    {"codigo": "MXN", "nombre": "Peso mexicano", "tipo_cambio_clp": 55.0},
    {"codigo": "PEN", "nombre": "Sol peruano", "tipo_cambio_clp": 255.0},
    {"codigo": "ARS", "nombre": "Peso argentino", "tipo_cambio_clp": 1.05},
    {"codigo": "BRL", "nombre": "Real brasileño", "tipo_cambio_clp": 175.0},
    {"codigo": "GBP", "nombre": "Libra esterlina", "tipo_cambio_clp": 1210.0},
]

MONEDAS_POR_CODIGO = {m["codigo"]: m for m in MONEDAS}


def convertir_a_clp(monto, codigo_moneda):
    moneda = MONEDAS_POR_CODIGO.get(codigo_moneda, MONEDAS_POR_CODIGO[MONEDA_BASE])
    return monto * moneda["tipo_cambio_clp"]
