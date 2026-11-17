"""Tendencias, comparativos y alertas simples para la sección Toma de
Decisiones, calculados a partir de los mismos balances clasificados que
alimentan el Estado de Rendimiento Financiero (paso 1: Subir Información
Contable). No se sube nada nuevo aquí: se reutiliza el historial de
balances ya cargado.
"""
from cuentas_ventas import es_costo_ventas as _es_costo_ventas, es_venta as _es_venta
from estado_financiero import construir_estado

UMBRAL_ALERTA_PORCENTAJE = 20  # variación mínima (%) para generar una alerta
UMBRAL_ALERTA_PUNTOS_PORCENTUALES = 5


def _ingresos_del_balance(cuentas):
    cuentas_ventas = [
        cuenta
        for cuenta in cuentas
        if cuenta.categoria_niif == "Operación" and _es_venta(cuenta.nombre)
    ]
    if not cuentas_ventas:
        return None
    ingresos = sum(cuenta.importe for cuenta in cuentas_ventas)
    return abs(ingresos) if ingresos < 0 else ingresos


def _costos_ventas_del_balance(cuentas):
    cuentas_costo_ventas = [
        cuenta
        for cuenta in cuentas
        if cuenta.categoria_niif == "Operación" and _es_costo_ventas(cuenta.nombre)
    ]
    return sum(cuenta.importe for cuenta in cuentas_costo_ventas) if cuentas_costo_ventas else None


def _gastos_operativos_del_balance(cuentas):
    cuentas_gastos = [
        cuenta
        for cuenta in cuentas
        if cuenta.categoria_niif == "Operación"
        and cuenta.importe < 0
        and not _es_venta(cuenta.nombre)
        and not _es_costo_ventas(cuenta.nombre)
    ]
    return sum(abs(cuenta.importe) for cuenta in cuentas_gastos) if cuentas_gastos else None


def _margen(numerador, ingresos):
    return (
        numerador / ingresos * 100
        if numerador is not None and ingresos is not None and ingresos > 0
        else None
    )


def _variacion_puntos_porcentuales(actual, anterior):
    return actual - anterior if actual is not None and anterior is not None else None


def _variacion_porcentual(actual, anterior):
    if actual is None or anterior is None or anterior == 0:
        return None
    return (actual - anterior) / abs(anterior) * 100


def _historial_por_periodo(empresa):
    """Un resumen por periodo con informe generado y cuentas revisadas."""
    balances_por_periodo = {}
    cuentas_por_balance = {}
    for balance in empresa.balances:
        cuentas_revisadas = [cuenta for cuenta in balance.cuentas if cuenta.revisado]
        if (
            balance.periodo not in balances_por_periodo
            and balance.informes
            and cuentas_revisadas
        ):
            balances_por_periodo[balance.periodo] = balance
            cuentas_por_balance[balance.periodo] = cuentas_revisadas

    historial = []
    for periodo in sorted(balances_por_periodo.keys()):
        balance = balances_por_periodo[periodo]
        cuentas = cuentas_por_balance[periodo]
        _, resumen = construir_estado(cuentas)
        ingresos = _ingresos_del_balance(cuentas)
        costo_ventas = _costos_ventas_del_balance(cuentas)
        gastos_operativos = _gastos_operativos_del_balance(cuentas)
        ganancia_bruta = ingresos + costo_ventas if ingresos is not None and costo_ventas is not None else None
        historial.append(
            {
                "periodo": periodo,
                "balance": balance,
                "resumen": resumen,
                "ingresos": ingresos,
                "costo_ventas": costo_ventas,
                "gastos_operativos": gastos_operativos,
                "ganancia_bruta": ganancia_bruta,
                "margen_bruto": _margen(ganancia_bruta, ingresos),
                "margen_operativo": _margen(resumen["resultado_operativo"], ingresos),
                "razon_costo_ventas": _margen(abs(costo_ventas), ingresos)
                if costo_ventas is not None
                else None,
                "razon_gastos_operativos": _margen(gastos_operativos, ingresos),
            }
        )
    return historial


def calcular_tendencias(empresa):
    return _historial_por_periodo(empresa)


def preparar_grafico_margenes(historial):
    definiciones = (
        ("margen_bruto", "Margen bruto", "#1d9a6c"),
        ("margen_operativo", "Margen operativo", "#6d3df0"),
    )
    valores = [
        periodo[clave]
        for periodo in historial
        for clave, _, _ in definiciones
        if periodo[clave] is not None
    ]
    if not valores:
        return None

    ancho = max(720, 72 * max(len(historial) - 1, 1) + 72)
    alto = 270
    izquierda, derecha, arriba, abajo = 56, 20, 20, 38
    ancho_grafico = ancho - izquierda - derecha
    alto_grafico = alto - arriba - abajo
    minimo = min(0.0, min(valores))
    maximo = max(0.0, max(valores))
    rango = maximo - minimo
    if rango == 0:
        minimo, maximo = -0.5, 0.5
        rango = 1
    relleno = max(rango * 0.12, 1.0)
    minimo -= relleno
    maximo += relleno

    def posicion_y(valor):
        return arriba + (maximo - valor) / (maximo - minimo) * alto_grafico

    periodos = []
    for indice, item in enumerate(historial):
        x = (
            izquierda + ancho_grafico / 2
            if len(historial) == 1
            else izquierda + indice * ancho_grafico / (len(historial) - 1)
        )
        periodos.append({"etiqueta": str(item["periodo"]), "x": round(x, 2)})

    ticks = []
    for indice in range(5):
        valor = maximo - indice * (maximo - minimo) / 4
        ticks.append({"valor": round(valor, 1), "y": round(posicion_y(valor), 2)})

    series = []
    for clave, etiqueta, color in definiciones:
        segmentos = []
        puntos = []
        segmento_actual = []
        for periodo, posicion in zip(historial, periodos):
            valor = periodo[clave]
            if valor is None:
                if segmento_actual:
                    segmentos.append(" ".join(segmento_actual))
                    segmento_actual = []
                continue
            y = posicion_y(valor)
            segmento_actual.append(f"{posicion['x']:.2f},{y:.2f}")
            puntos.append(
                {
                    "x": posicion["x"],
                    "y": round(y, 2),
                    "periodo": str(periodo["periodo"]),
                    "valor": round(valor, 1),
                }
            )
        if segmento_actual:
            segmentos.append(" ".join(segmento_actual))
        series.append(
            {"etiqueta": etiqueta, "color": color, "segmentos": segmentos, "puntos": puntos}
        )

    return {
        "ancho": ancho,
        "alto": alto,
        "izquierda": izquierda,
        "derecha": derecha,
        "abajo": alto - abajo,
        "cero_y": round(posicion_y(0), 2),
        "periodos": periodos,
        "ticks": ticks,
        "series": series,
    }


def calcular_comparativos(empresa):
    historial = _historial_por_periodo(empresa)
    if not historial:
        return None

    actual = historial[-1]
    anterior = historial[-2] if len(historial) > 1 else None

    return {
        "periodo_actual": actual["periodo"],
        "periodo_anterior": anterior["periodo"] if anterior else None,
        "ingresos_actuales": actual["ingresos"],
        "ingresos_anteriores": anterior["ingresos"] if anterior else None,
        "variacion_ventas_pct": _variacion_porcentual(
            actual["ingresos"], anterior["ingresos"] if anterior else None
        ),
        "costo_ventas_actual": actual["costo_ventas"],
        "costo_ventas_anterior": anterior["costo_ventas"] if anterior else None,
        "variacion_costo_ventas_pct": _variacion_porcentual(
            abs(actual["costo_ventas"]) if actual["costo_ventas"] is not None else None,
            abs(anterior["costo_ventas"])
            if anterior and anterior["costo_ventas"] is not None
            else None,
        ),
        "ganancia_bruta_actual": actual["ganancia_bruta"],
        "ganancia_bruta_anterior": anterior["ganancia_bruta"] if anterior else None,
        "variacion_ganancia_bruta_pct": _variacion_porcentual(
            actual["ganancia_bruta"], anterior["ganancia_bruta"] if anterior else None
        ),
        "resultado_operativo_actual": actual["resumen"]["resultado_operativo"],
        "resultado_operativo_anterior": anterior["resumen"]["resultado_operativo"] if anterior else None,
        "variacion_resultado_operativo_pct": _variacion_porcentual(
            actual["resumen"]["resultado_operativo"],
            anterior["resumen"]["resultado_operativo"] if anterior else None,
        ),
        "margen_bruto_actual": actual["margen_bruto"],
        "margen_bruto_anterior": anterior["margen_bruto"] if anterior else None,
        "variacion_margen_bruto_pp": _variacion_puntos_porcentuales(
            actual["margen_bruto"], anterior["margen_bruto"] if anterior else None
        ),
        "margen_operativo_actual": actual["margen_operativo"],
        "margen_operativo_anterior": anterior["margen_operativo"] if anterior else None,
        "variacion_margen_operativo_pp": _variacion_puntos_porcentuales(
            actual["margen_operativo"], anterior["margen_operativo"] if anterior else None
        ),
    }


def calcular_alertas(empresa):
    historial = _historial_por_periodo(empresa)
    alertas = []
    if not historial:
        return alertas

    actual = historial[-1]
    resultado_operativo = actual["resumen"]["resultado_operativo"]
    if actual["ganancia_bruta"] is not None and actual["ganancia_bruta"] < 0:
        alertas.append(
            {
                "severidad": "danger",
                "titulo": "El costo de ventas supera las ventas",
                "detalle": "La empresa presenta una pérdida bruta en el periodo actual.",
                "sugerencia": (
                    "Revisar precios, descuentos, compras y costo de productos en el libro mayor; "
                    "confirmar también la clasificación de ventas y costos."
                ),
            }
        )

    if resultado_operativo < 0:
        alertas.append(
            {
                "severidad": "danger",
                "titulo": "Resultado operativo negativo",
                "detalle": "Los ingresos operativos no alcanzan para cubrir los costos y gastos operativos registrados.",
                "sugerencia": (
                    "Revisar las cuentas de gasto con mayor importe, validar sus movimientos y analizar "
                    "opciones de precio, ventas y costos antes de aplicar recortes."
                ),
            }
        )

    if len(historial) < 2:
        return alertas

    anterior = historial[-2]
    variacion_ventas = _variacion_porcentual(actual["ingresos"], anterior["ingresos"])
    if variacion_ventas is not None and variacion_ventas <= -UMBRAL_ALERTA_PORCENTAJE:
        alertas.append(
            {
                "severidad": "warning",
                "titulo": "Disminución significativa de ventas",
                "detalle": f"Las ventas bajaron {abs(variacion_ventas):.1f}% respecto del periodo anterior.",
                "sugerencia": (
                    "Comparar las cuentas de ventas y sus movimientos por cliente, producto y fecha; "
                    "revisar cambios de precio, volumen y estacionalidad."
                ),
            }
        )

    costo_actual = actual["razon_costo_ventas"]
    costo_anterior = anterior["razon_costo_ventas"]
    if (
        costo_actual is not None
        and costo_anterior is not None
        and costo_actual - costo_anterior >= UMBRAL_ALERTA_PUNTOS_PORCENTUALES
    ):
        alertas.append(
            {
                "severidad": "warning",
                "titulo": "El costo de ventas consume una mayor proporción de las ventas",
                "detalle": (
                    f"La proporción aumentó {costo_actual - costo_anterior:.1f} puntos porcentuales "
                    "respecto del periodo anterior."
                ),
                "sugerencia": (
                    "Revisar en el libro mayor compras, costos por producto, descuentos y movimientos "
                    "inusuales; contrastar precios de proveedores y precios de venta."
                ),
            }
        )

    gastos_actuales = actual["razon_gastos_operativos"]
    gastos_anteriores = anterior["razon_gastos_operativos"]
    if (
        gastos_actuales is not None
        and gastos_anteriores is not None
        and gastos_actuales - gastos_anteriores >= UMBRAL_ALERTA_PUNTOS_PORCENTUALES
    ):
        alertas.append(
            {
                "severidad": "warning",
                "titulo": "Los gastos operativos crecen frente a las ventas",
                "detalle": (
                    f"El peso de los gastos operativos aumentó "
                    f"{gastos_actuales - gastos_anteriores:.1f} puntos porcentuales."
                ),
                "sugerencia": (
                    "Ordenar las cuentas operativas por aumento e importe, revisar sus movimientos y "
                    "distinguir gastos recurrentes de extraordinarios antes de ajustar presupuestos."
                ),
            }
        )

    margen_actual = actual["margen_operativo"]
    margen_anterior = anterior["margen_operativo"]
    deterioro_margen = _variacion_puntos_porcentuales(margen_actual, margen_anterior)
    if deterioro_margen is not None and deterioro_margen <= -UMBRAL_ALERTA_PUNTOS_PORCENTUALES:
        alertas.append(
            {
                "severidad": "warning",
                "titulo": "Deterioro del margen operativo",
                "detalle": f"El margen operativo disminuyó {abs(deterioro_margen):.1f} puntos porcentuales.",
                "sugerencia": (
                    "Revisar qué cuentas explican la variación y contrastar el crecimiento de ventas, "
                    "costo de ventas y gastos operativos."
                ),
            }
        )
    return alertas
