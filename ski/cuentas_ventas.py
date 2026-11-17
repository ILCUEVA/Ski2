"""Identificación de las cuentas de ventas y de costo de ventas.

Se usa para calcular la Ganancia bruta (ingresos de actividades ordinarias
menos costo de ventas) en el Estado de Rendimiento Financiero y para los
márgenes de Tendencias, de modo que ambas pantallas coincidan.
"""
import re
import unicodedata

_PATRON_VENTA = re.compile(r"\bventas?\b")

_NO_ES_VENTA = (
    "perdida en venta",
    "ganancia en venta",
    "venta de activo",
    "venta de maquinaria",
    "otros ingreso",
    "ingreso financiero",
    "ingresos financieros",
    "interes",
    "diferencia de cambio",
    "dividendo",
    "arriendo de propiedad",
    "discontinuad",
)

_PRESTACION_SERVICIOS = ("servicios prestados", "prestacion de servicios")

_NO_ES_COSTO_VENTAS = (
    "financ",
    "interes",
    "prestamo",
    "leasing",
    "impuesto",
    "comision",
    "discontinuad",
)


def normalizar(texto):
    texto = (texto or "").lower()
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )


def es_venta(nombre):
    """Ingresos de actividades ordinarias: ventas, ingresos por obras o servicios,
    y sus devoluciones o descuentos. Excluye costos, gastos, otros ingresos,
    ingresos financieros y resultados por venta de activos."""
    nombre = normalizar(nombre)
    if "costo" in nombre or "gasto" in nombre:
        return False
    if any(termino in nombre for termino in _NO_ES_VENTA):
        return False
    return (
        bool(_PATRON_VENTA.search(nombre))
        or nombre.startswith("ingreso")
        or any(termino in nombre for termino in _PRESTACION_SERVICIOS)
    )


def es_costo_ventas(nombre):
    """Costos directamente atribuibles a lo vendido: cuentas «Costo de ...»
    (materiales, mano de obra directa, subcontratos, etc.)."""
    nombre = normalizar(nombre)
    if any(termino in nombre for termino in _NO_ES_COSTO_VENTAS):
        return False
    return nombre.startswith("costo") or "costo de venta" in nombre
