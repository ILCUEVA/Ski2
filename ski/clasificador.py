"""Clasificador heurístico de cuentas de resultado según NIIF 18 (párr. 47-53, 59-68).

El importador solo trae el nombre de cada cuenta (sin un campo de "tipo"
explícito), así que la clasificación se hace por palabras clave sobre el
nombre. Los criterios siguen el material de referencia NIIF 18:

- Operación: categoría "por defecto" (párr. 52) — ingresos ordinarios, costo
  de ventas, gastos de administración/venta, depreciación de activos
  operacionales, deterioro de cuentas por cobrar (NIIF 9, párr. B57) y
  diferencias de cambio (clasificadas como operación según el criterio usado).
- Inversión: resultados de inversiones en asociadas/negocios conjuntos
  (método de la participación, párr. 53.a) e ingresos financieros, salvo
  derivados usados para cobertura de operación (p.61).
- Financiación: intereses y costos de préstamos, arrendamientos y bonos
  emitidos (párr. 59-60, 53), incluido su reajuste; los "otros reajustes" y
  el reajuste por PPM van a operación.
- Impuesto a las ganancias: impuesto corriente y diferido (párr. 67, NIC 12).
- Operaciones discontinuadas: resultados de actividades discontinuadas
  (párr. 68, NIIF 5).

Cada cuenta clasificada queda "pendiente de revisión" para que el usuario la
confirme o ajuste manualmente; `motivo_clasificacion` entrega el criterio
usado para que el usuario entienda por qué se sugirió esa categoría.
"""
import unicodedata

from models import CATEGORIAS_NIIF

OPERACION, INVERSION, FINANCIACION, IMPUESTO, DISCONTINUADAS = CATEGORIAS_NIIF


def _normalizar(texto):
    texto = texto.lower().strip()
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


# Se evalúan primero: aunque el nombre calce con una regla de más abajo, estos
# casos siempre se clasifican como Operación.
_EXCEPCIONES = [
    (
        ["diferencia de cambio", "diferencias de cambio"],
        OPERACION,
        "Las diferencias de cambio se clasifican en Operación, según el criterio adoptado para esta clasificación.",
    ),
    (
        ["reajuste ppm", "otro reajuste", "otros reajustes"],
        OPERACION,
        "Los reajustes distintos al de bonos o pasivos por arrendamiento (p. ej. PPM) se clasifican en Operación (NIIF 18, párr. 53).",
    ),
    (
        ["derivado", "cobertura"],
        OPERACION,
        "Los resultados de derivados usados para cobertura de la operación (p. ej. pagos de importaciones) se clasifican en Operación (NIIF 18, párr. 61).",
    ),
]

# Reglas evaluadas en orden; gana la primera palabra clave que calce.
_REGLAS = [
    (
        ["operaciones discontinuadas", "operacion discontinuada", "discontinuada"],
        DISCONTINUADAS,
        "Corresponde a una operación discontinuada (NIIF 18, párr. 68; NIIF 5).",
    ),
    (
        ["impuesto a las ganancias", "impuesto a la renta", "impuesto renta",
         "impuesto corriente", "impuesto diferido", "ppm"],
        IMPUESTO,
        "Corresponde a impuesto a las ganancias, corriente o diferido (NIIF 18, párr. 67; NIC 12).",
    ),
    (
        ["gasto financiero", "gastos financieros", "costo financiero", "costos financieros",
         "interes", "prestamo", "préstamo", "bono", "arrendamiento financiero",
         "pasivo por arrendamiento", "comision bancaria", "comisiones bancarias"],
        FINANCIACION,
        "Los intereses y costos de préstamos, bonos o arrendamientos financieros se clasifican en Financiación (NIIF 18, párr. 53 y 59-60).",
    ),
    (
        ["inversion", "inversiones", "asociada", "asociadas", "negocio conjunto", "negocios conjuntos",
         "metodo de la participacion", "dividendo", "ingreso financiero", "ingresos financieros"],
        INVERSION,
        "Los ingresos financieros y los resultados de inversiones en asociadas o negocios conjuntos se clasifican en Inversión (NIIF 18, párr. 53.a).",
    ),
]

_MOTIVO_OPERACION_DEFECTO = (
    "Se sugiere Operación por ser la categoría por defecto (NIIF 18, párr. 52): agrupa todo ingreso "
    "o gasto que no corresponda a inversión, financiación, impuesto a las ganancias u operaciones discontinuadas."
)


def _evaluar(nombre_cuenta):
    nombre = _normalizar(nombre_cuenta)
    for palabras, categoria, motivo in _EXCEPCIONES:
        if any(p in nombre for p in palabras):
            return categoria, motivo
    for palabras, categoria, motivo in _REGLAS:
        if any(p in nombre for p in palabras):
            return categoria, motivo
    return OPERACION, _MOTIVO_OPERACION_DEFECTO


def _texto_a_evaluar(nombre_cuenta, observacion=None):
    if observacion:
        return f"{nombre_cuenta} {observacion}"
    return nombre_cuenta


def clasificar_cuenta(nombre_cuenta, observacion=None):
    categoria, _ = _evaluar(_texto_a_evaluar(nombre_cuenta, observacion))
    return categoria


def motivo_clasificacion(nombre_cuenta, observacion=None):
    _, motivo = _evaluar(_texto_a_evaluar(nombre_cuenta, observacion))
    if observacion:
        motivo += f' Se consideró también tu observación: "{observacion}".'
    return motivo
