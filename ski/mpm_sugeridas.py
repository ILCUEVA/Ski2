"""Sugerencias simples de MPM (Medidas de Rendimiento Definidas por la Gerencia,
NIIF 18) calculadas a partir de las cuentas ya clasificadas del balance más
reciente. Son versiones simplificadas pensadas para que una pyme pueda
adoptarlas rápido; no reemplazan un análisis financiero detallado.
"""
import unicodedata

PALABRAS_DEPRECIACION = ["depreciacion", "amortizacion"]
PALABRAS_NO_RECURRENTE = ["otros ingreso", "otros gasto", "extraordinari", "no recurrente"]

TODAS_LAS_MPM = ["EBIT", "EBITDA", "Resultado Operacional Ajustado", "Flujo de Caja Libre (aproximado)"]

# Qué MPM son más relevantes según el rubro de la empresa. Es un criterio
# simplificado (ej. EBITDA pesa más en rubros intensivos en activos fijos,
# donde la depreciación es significativa); no reemplaza el juicio del
# contador de la empresa.
RUBROS_MPM_SUGERIDAS = {
    "Finanzas": ["EBIT", "Resultado Operacional Ajustado"],
    "Constructoras": ["EBITDA", "EBIT", "Flujo de Caja Libre (aproximado)"],
    "Comercial": ["EBIT", "Resultado Operacional Ajustado"],
    "Servicios profesionales": ["EBIT", "Resultado Operacional Ajustado"],
    "Restaurantes y cafés": ["EBITDA", "Resultado Operacional Ajustado"],
    "Manufactura": ["EBITDA", "EBIT", "Flujo de Caja Libre (aproximado)"],
    "Tecnología": ["EBITDA", "EBIT"],
    "Transporte y logística": ["EBITDA", "Flujo de Caja Libre (aproximado)"],
    "Farmacia": ["EBIT", "Resultado Operacional Ajustado"],
}


def mpm_sugeridas_por_rubro(rubro):
    return RUBROS_MPM_SUGERIDAS.get(rubro, TODAS_LAS_MPM)


def _normalizar(texto):
    texto = (texto or "").lower()
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def calcular_mpm_sugeridas(cuentas, resumen, rubro=None):
    """cuentas: lista de CuentaContable del balance más reciente.
    resumen: el dict devuelto por estado_financiero.construir_estado().
    rubro: rubro de la empresa, para filtrar solo las MPM relevantes para ese rubro."""
    depreciacion_amortizacion = sum(
        abs(c.importe) for c in cuentas if any(p in _normalizar(c.nombre) for p in PALABRAS_DEPRECIACION)
    )
    ajustes_no_recurrentes = sum(
        c.importe for c in cuentas if any(p in _normalizar(c.nombre) for p in PALABRAS_NO_RECURRENTE)
    )
    impuestos = sum(c.importe for c in cuentas if c.categoria_niif == "Impuestos a las ganancias")

    ebit = resumen["resultado_antes_financiacion_impuestos"]
    ebitda = ebit + depreciacion_amortizacion
    resultado_operacional_ajustado = resumen["resultado_operativo"] - ajustes_no_recurrentes
    flujo_caja_aproximado = ebitda + impuestos  # impuestos ya viene con signo negativo

    todas = [
        {
            "nombre": "EBIT",
            "descripcion": "Resultado antes de intereses (financiación) e impuestos a las ganancias.",
            "formula": "Resultado operativo + Resultado de inversión",
            "valor": ebit,
        },
        {
            "nombre": "EBITDA",
            "descripcion": "EBIT sin el efecto de depreciación y amortización del periodo.",
            "formula": "EBIT + Depreciación y amortización",
            "valor": ebitda,
        },
        {
            "nombre": "Resultado Operacional Ajustado",
            "descripcion": "Resultado operativo excluyendo otros ingresos/gastos atípicos o no recurrentes.",
            "formula": "Resultado operativo − otros ingresos/gastos no recurrentes",
            "valor": resultado_operacional_ajustado,
        },
        {
            "nombre": "Flujo de Caja Libre (aproximado)",
            "descripcion": (
                "Estimación simple a partir del EBITDA. No considera inversión en activos (capex) ni "
                "variación de capital de trabajo, así que es solo una aproximación."
            ),
            "formula": "EBITDA + Impuestos a las ganancias",
            "valor": flujo_caja_aproximado,
            "aproximado": True,
        },
    ]

    nombres_permitidos = mpm_sugeridas_por_rubro(rubro)
    return [m for m in todas if m["nombre"] in nombres_permitidos]
