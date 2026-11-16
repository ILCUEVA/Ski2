"""Lectura del importador de balance (hoja 'Balance') y validación del libro mayor.

El importador de balance sigue el formato de Importador_balance.xlsx: una
fila de cuenta por línea, con columnas Débito/Crédito/Deudor/Acreedor/
Activo/Pasivo/Pérdida/Ganancia. Solo interesan para la clasificación las
cuentas de resultado, es decir, las que tienen un monto en Pérdida o
Ganancia (las de Activo/Pasivo son del balance, no del estado de resultados).
"""
import re
import unicodedata

import openpyxl

COLUMNAS_RESULTADO = ("cuenta", "debito", "credito", "deudor", "acreedor", "activo", "pasivo", "perdida", "ganancia")

FILAS_A_IGNORAR = {
    "subtotal",
    "totales",
    "total",
    "utilidad / perdida del ejercicio",
    "utilidad / pérdida del ejercicio",
    "resultado del ejercicio",
}


class ImportadorInvalido(ValueError):
    pass


def _a_float(valor):
    """Convierte una celda a float; si no es un número válido (texto suelto,
    un encabezado repetido, etc.) devuelve None en vez de lanzar una excepción."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def leer_cuentas_resultado(archivo):
    """archivo: stream (.xlsx) con la hoja 'Balance'. Devuelve una lista de
    dicts {"nombre": str, "importe": float} para cada cuenta de resultado."""
    try:
        wb = openpyxl.load_workbook(archivo, data_only=True)
    except Exception as exc:  # noqa: BLE001 - cualquier archivo corrupto o no-excel
        raise ImportadorInvalido("El archivo de balance no es un .xlsx válido.") from exc

    if "Balance" not in wb.sheetnames:
        raise ImportadorInvalido("El archivo de balance debe tener una hoja llamada 'Balance'.")

    ws = wb["Balance"]
    cuentas = []
    for fila in ws.iter_rows(min_row=3, values_only=True):
        nombre = fila[0]
        if not nombre:
            continue
        if str(nombre).strip().lower() in FILAS_A_IGNORAR:
            continue
        perdida = _a_float(fila[7])
        ganancia = _a_float(fila[8])
        if not perdida and not ganancia:
            continue  # cuenta de activo/pasivo, o fila no numérica: no es de resultado
        importe = (ganancia or 0) - (perdida or 0)
        cuentas.append({"nombre": str(nombre).strip(), "importe": importe})

    if not cuentas:
        raise ImportadorInvalido("No se encontraron cuentas de resultado (ingresos o gastos) en el archivo.")
    return cuentas


def validar_libro_mayor(archivo):
    """Valida que el libro mayor sea un .xlsx legible y devuelve sus nombres de hoja
    (una hoja esperada por cada cuenta de resultado)."""
    try:
        wb = openpyxl.load_workbook(archivo, data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ImportadorInvalido("El archivo de libro mayor no es un .xlsx válido.") from exc
    return wb.sheetnames


def leer_movimientos_libro_mayor(archivo):
    """archivo: stream (.xlsx) del libro mayor, una hoja por cuenta (formato de
    Importador_libro_mayor.xlsx: fila 1 "Nombre de la cuenta:", fila 2 encabezados,
    datos desde la fila 3). Devuelve {nombre_cuenta: [movimientos]}, donde cada
    movimiento es un dict con fecha, num_transaccion, detalle, debe, haber,
    saldo_deudor y saldo_acreedor.

    El nombre de cuenta se toma de la celda junto a "Nombre de la cuenta:"
    (fila 1) y, si falta, del nombre de la hoja — el nombre de la hoja de
    Excel puede venir truncado o reescrito y no siempre calza con el nombre
    tal cual aparece en el balance."""
    try:
        wb = openpyxl.load_workbook(archivo, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ImportadorInvalido("El archivo de libro mayor no es un .xlsx válido.") from exc

    movimientos_por_cuenta = {}
    for hoja in wb.sheetnames:
        ws = wb[hoja]
        primera_fila = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        nombre_celda = primera_fila[1] if primera_fila and len(primera_fila) > 1 else None
        nombre_cuenta = str(nombre_celda).strip() if nombre_celda else hoja.strip()

        movimientos = []
        for fila in ws.iter_rows(min_row=3, max_col=7, values_only=True):
            fecha = fila[0]
            if fecha is None:
                continue
            movimientos.append({
                "fecha": fecha,
                "num_transaccion": fila[1],
                "detalle": fila[2],
                "debe": _a_float(fila[3]) or 0,
                "haber": _a_float(fila[4]) or 0,
                "saldo_deudor": _a_float(fila[5]) or 0,
                "saldo_acreedor": _a_float(fila[6]) or 0,
            })
        movimientos_por_cuenta[nombre_cuenta] = movimientos
    return movimientos_por_cuenta


def _normalizar_nombre(texto):
    """Uppercase, sin tildes, sin espacios repetidos y sin un eventual código
    inicial (ej. "4010110 - ", "41-01-01 "), para poder comparar el nombre de
    una cuenta del balance contra el nombre/hoja del libro mayor aunque no
    coincidan letra por letra."""
    if not texto:
        return ""
    texto = str(texto).strip().upper()
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    texto = re.sub(r"^[\d.\-\s]+(?=[A-ZÑ])", "", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def buscar_movimientos(movimientos_por_cuenta, nombre_cuenta):
    """Busca los movimientos de una cuenta del balance dentro del libro mayor,
    tolerando diferencias de mayúsculas/tildes/espacios o de un código inicial
    entre el nombre de la cuenta en el balance y el nombre usado en el libro
    mayor (coincidencia exacta primero, luego normalizada, luego parcial)."""
    if nombre_cuenta in movimientos_por_cuenta:
        return movimientos_por_cuenta[nombre_cuenta]

    objetivo = _normalizar_nombre(nombre_cuenta)
    if not objetivo:
        return []

    candidato_parcial = None
    for nombre_libro_mayor, movimientos in movimientos_por_cuenta.items():
        normalizado = _normalizar_nombre(nombre_libro_mayor)
        if normalizado == objetivo:
            return movimientos
        if candidato_parcial is None and normalizado and (normalizado in objetivo or objetivo in normalizado):
            candidato_parcial = movimientos

    return candidato_parcial or []
