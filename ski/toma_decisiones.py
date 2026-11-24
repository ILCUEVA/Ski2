"""Tendencias, comparativos y alertas simples para la sección Toma de
Decisiones, calculados a partir de los mismos balances clasificados que
alimentan el Estado de Rendimiento Financiero (paso 1: Subir Información
Contable). No se sube nada nuevo aquí: se reutiliza el historial de
balances ya cargado.
"""
from cuentas_ventas import es_costo_ventas as _es_costo_ventas, es_venta as _es_venta
from estado_financiero import construir_estado

UMBRALES_POR_DEFECTO = {
    "caida_ventas_pct": 20,  # baja mínima de ventas (%) para alertar
    "puntos_por_cada_100": 5,  # aumento mínimo del peso de costos/gastos, o caída del margen
}

# Criterio orientativo propio (no proviene de promedios publicados del sector): rubros con ventas
# más variables toleran una caída mayor antes de alertar; rubros con márgenes ajustados alertan
# con variaciones más pequeñas. Ajustar aquí los valores de cada rubro.
UMBRALES_POR_RUBRO = {
    "Constructoras": {"caida_ventas_pct": 25, "puntos_por_cada_100": 6},
    "Comercial": {"caida_ventas_pct": 15, "puntos_por_cada_100": 3},
    "Farmacia": {"caida_ventas_pct": 10, "puntos_por_cada_100": 2},
    "Servicios profesionales": {"caida_ventas_pct": 20, "puntos_por_cada_100": 5},
    "Restaurantes y cafés": {"caida_ventas_pct": 20, "puntos_por_cada_100": 4},
    "Manufactura": {"caida_ventas_pct": 20, "puntos_por_cada_100": 4},
    "Tecnología": {"caida_ventas_pct": 25, "puntos_por_cada_100": 6},
    "Transporte y logística": {"caida_ventas_pct": 15, "puntos_por_cada_100": 3},
}


def umbrales_del_rubro(rubro):
    return {**UMBRALES_POR_DEFECTO, **UMBRALES_POR_RUBRO.get(rubro, {})}


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
                "cuentas": cuentas,
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


def _es_gasto_operativo(cuenta):
    return (
        cuenta.categoria_niif == "Operación"
        and cuenta.importe < 0
        and not _es_venta(cuenta.nombre)
        and not _es_costo_ventas(cuenta.nombre)
    )


def _es_cuenta_venta(cuenta):
    return cuenta.categoria_niif == "Operación" and _es_venta(cuenta.nombre)


def _es_cuenta_costo_ventas(cuenta):
    return cuenta.categoria_niif == "Operación" and _es_costo_ventas(cuenta.nombre)


def _monto_simple(valor):
    valor = abs(valor)
    if valor >= 1_000_000:
        texto = f"{valor / 1_000_000:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")
        if texto.endswith(",0"):
            texto = texto[:-2]
        return f"{texto} millones"
    return f"{valor:,.0f}".replace(",", ".")


def _montos_por_cuenta(item, seleccion, signo):
    """Monto por nombre de cuenta; signo=-1 para mostrar costos y gastos como positivos."""
    montos = {}
    for cuenta in item["cuentas"]:
        if seleccion(cuenta):
            montos[cuenta.nombre] = montos.get(cuenta.nombre, 0) + signo * cuenta.importe
    return montos


def _cuentas_que_mas_cambiaron(actual, anterior, seleccion, signo, sentido, limite=3):
    """Cuentas con mayor cambio entre periodos, con una frase fácil de leer.
    sentido: 'baja', 'sube' o 'ambos'."""
    previos = _montos_por_cuenta(anterior, seleccion, signo)
    actuales = _montos_por_cuenta(actual, seleccion, signo)
    filas = []
    for nombre in set(previos) | set(actuales):
        antes = previos.get(nombre, 0)
        ahora = actuales.get(nombre, 0)
        diferencia = ahora - antes
        if diferencia == 0 or (sentido == "baja" and diferencia > 0) or (sentido == "sube" and diferencia < 0):
            continue
        filas.append((abs(diferencia), nombre, antes, ahora, diferencia))
    filas.sort(reverse=True)
    resultado = []
    for _, nombre, antes, ahora, diferencia in filas[:limite]:
        verbo = "Subió" if diferencia > 0 else "Bajó"
        cambio = "más" if diferencia > 0 else "menos"
        resultado.append(
            {
                "nombre": nombre,
                "texto": (
                    f"{verbo} de {_monto_simple(antes)} a {_monto_simple(ahora)} "
                    f"({_monto_simple(diferencia)} {cambio})."
                ),
            }
        )
    return resultado


def _cuentas_de_mayor_monto(item, seleccion, signo, limite=3):
    montos = _montos_por_cuenta(item, seleccion, signo)
    ordenadas = sorted(montos.items(), key=lambda par: par[1], reverse=True)[:limite]
    return [
        {"nombre": nombre, "texto": f"Suma {_monto_simple(monto)} en el periodo."}
        for nombre, monto in ordenadas
        if monto > 0
    ]


def _grupo(titulo, cuentas):
    return {"titulo": titulo, "cuentas": cuentas} if cuentas else None


def _grupos(*grupos):
    return [grupo for grupo in grupos if grupo]


def _periodo_texto(item):
    return str(item["periodo"])


def _explicar_costos_vs_ventas(actual, anterior, costo_actual, costo_anterior):
    variacion_ventas = _variacion_porcentual(actual["ingresos"], anterior["ingresos"])
    variacion_costos = _variacion_porcentual(
        abs(actual["costo_ventas"]), abs(anterior["costo_ventas"])
    )
    if variacion_ventas is None or variacion_costos is None:
        return (
            f"Hoy {costo_actual:.0f} de cada 100 que vendes se destinan a costos directos; "
            f"antes eran {costo_anterior:.0f}. Queda menos dinero para pagar los demás gastos."
        )

    def describir(variacion):
        return f"{'subieron' if variacion > 0 else 'bajaron'} {abs(variacion):.1f}%"

    return (
        f"Tus ventas {describir(variacion_ventas)}, pero tus costos directos {describir(variacion_costos)}. "
        "Como los costos no se redujeron en la misma medida que las ventas, "
        f"de cada 100 que vendes ahora quedan {100 - costo_actual:.0f} (antes {100 - costo_anterior:.0f}) "
        "para pagar los demás gastos y generar ganancia."
    )


def calcular_alertas(empresa):
    """Cada alerta incluye una explicación simple ("en_simple") y, cuando es posible,
    las cuentas que más influyen ("grupos") para usuarios sin formación contable."""
    historial = _historial_por_periodo(empresa)
    alertas = []
    if not historial:
        return alertas

    actual = historial[-1]
    anterior = historial[-2] if len(historial) > 1 else None
    umbrales = umbrales_del_rubro(empresa.rubro)
    resultado_operativo = actual["resumen"]["resultado_operativo"]
    if actual["ganancia_bruta"] is not None and actual["ganancia_bruta"] < 0:
        alertas.append(
            {
                "severidad": "danger",
                "titulo": "Lo que cuesta realizar tus ventas es mayor a lo que vendes",
                "detalle": (
                    f"En {_periodo_texto(actual)} vendiste {_monto_simple(actual['ingresos'])} y solo "
                    f"los costos directos (materiales, mano de obra, subcontratos) sumaron "
                    f"{_monto_simple(actual['costo_ventas'])}."
                ),
                "en_simple": "Cada venta te está dejando pérdida, incluso antes de pagar oficina, sueldos de administración u otros gastos.",
                "grupos": _grupos(
                    _grupo(
                        "Costos más altos",
                        _cuentas_de_mayor_monto(actual, _es_cuenta_costo_ventas, -1),
                    )
                ),
                "sugerencia": (
                    "Revisa si los precios de venta cubren lo que te cuesta producir o ejecutar el trabajo, "
                    "y si hay compras o descuentos fuera de lo normal."
                ),
            }
        )

    if resultado_operativo < 0:
        grupos = (
            _grupos(
                _grupo(
                    "Ventas que más bajaron",
                    _cuentas_que_mas_cambiaron(actual, anterior, _es_cuenta_venta, 1, "baja", 2),
                ),
                _grupo(
                    "Gastos que más subieron",
                    _cuentas_que_mas_cambiaron(actual, anterior, _es_gasto_operativo, -1, "sube", 2),
                ),
            )
            if anterior
            else _grupos(
                _grupo(
                    "Gastos más altos",
                    _cuentas_de_mayor_monto(actual, _es_gasto_operativo, -1),
                )
            )
        )
        alertas.append(
            {
                "severidad": "danger",
                "titulo": "Estás perdiendo dinero con tu actividad principal",
                "detalle": (
                    f"En {_periodo_texto(actual)}, lo que ingresó por ventas no alcanzó para pagar todos "
                    f"los costos y gastos del negocio. Faltaron {_monto_simple(resultado_operativo)}."
                ),
                "en_simple": "Los gastos del periodo superaron a las ventas.",
                "grupos": grupos,
                "sugerencia": (
                    "Mira primero las cuentas de arriba. Antes de recortar, revisa si puedes vender más "
                    "o ajustar precios."
                ),
            }
        )

    if anterior is None:
        return alertas

    variacion_ventas = _variacion_porcentual(actual["ingresos"], anterior["ingresos"])
    if variacion_ventas is not None and variacion_ventas <= -umbrales["caida_ventas_pct"]:
        ventas_que_bajaron = _cuentas_que_mas_cambiaron(
            actual, anterior, _es_cuenta_venta, 1, "baja", 3
        )
        principal = (
            f" La cuenta que más influye es «{ventas_que_bajaron[0]['nombre']}»." if ventas_que_bajaron else ""
        )
        alertas.append(
            {
                "severidad": "warning",
                "titulo": "Vendiste menos que en el periodo anterior",
                "detalle": (
                    f"Tus ventas bajaron {abs(variacion_ventas):.1f}%: pasaron de "
                    f"{_monto_simple(anterior['ingresos'])} en {_periodo_texto(anterior)} a "
                    f"{_monto_simple(actual['ingresos'])} en {_periodo_texto(actual)}."
                ),
                "en_simple": f"Los ingresos por ventas disminuyeron de forma importante.{principal}",
                "grupos": _grupos(_grupo("Ventas que más bajaron", ventas_que_bajaron)),
                "sugerencia": (
                    "Averigua si perdiste clientes, si terminaron proyectos o si cambiaron los precios "
                    "o la temporada."
                ),
            }
        )

    costo_actual = actual["razon_costo_ventas"]
    costo_anterior = anterior["razon_costo_ventas"]
    if (
        costo_actual is not None
        and costo_anterior is not None
        and costo_actual - costo_anterior >= umbrales["puntos_por_cada_100"]
    ):
        alertas.append(
            {
                "severidad": "warning",
                "titulo": "Producir o ejecutar lo que vendes te está costando más",
                "detalle": (
                    f"En {_periodo_texto(anterior)}, de cada 100 que vendías, {costo_anterior:.0f} se iban en "
                    f"costos directos (materiales, mano de obra, subcontratos). En {_periodo_texto(actual)} "
                    f"son {costo_actual:.0f}."
                ),
                "en_simple": _explicar_costos_vs_ventas(actual, anterior, costo_actual, costo_anterior),
                "grupos": _grupos(
                    _grupo(
                        "Costos que más cambiaron",
                        _cuentas_que_mas_cambiaron(
                            actual, anterior, _es_cuenta_costo_ventas, -1, "ambos", 3
                        ),
                    )
                ),
                "sugerencia": (
                    "Compara lo que pagas a proveedores y subcontratistas con lo que cobras, "
                    "y revisa descuentos o gastos inusuales."
                ),
            }
        )

    gastos_actuales = actual["razon_gastos_operativos"]
    gastos_anteriores = anterior["razon_gastos_operativos"]
    if (
        gastos_actuales is not None
        and gastos_anteriores is not None
        and gastos_actuales - gastos_anteriores >= umbrales["puntos_por_cada_100"]
    ):
        alertas.append(
            {
                "severidad": "warning",
                "titulo": "Los gastos de funcionamiento pesan más sobre tus ventas",
                "detalle": (
                    f"En {_periodo_texto(anterior)}, de cada 100 vendidos, {gastos_anteriores:.0f} se usaban en "
                    f"gastos como oficina, sueldos de administración o arriendos. En {_periodo_texto(actual)} "
                    f"son {gastos_actuales:.0f}."
                ),
                "en_simple": "Los gastos para mantener el negocio funcionando subieron mientras tus ventas bajaron.",
                "grupos": _grupos(
                    _grupo(
                        "Gastos que más subieron",
                        _cuentas_que_mas_cambiaron(actual, anterior, _es_gasto_operativo, -1, "sube", 3),
                    )
                ),
                "sugerencia": (
                    "Separa los gastos que se repiten todos los años de los que fueron únicos, "
                    "antes de decidir qué ajustar."
                ),
            }
        )

    margen_actual = actual["margen_operativo"]
    margen_anterior = anterior["margen_operativo"]
    deterioro_margen = _variacion_puntos_porcentuales(margen_actual, margen_anterior)
    if deterioro_margen is not None and deterioro_margen <= -umbrales["puntos_por_cada_100"]:
        ahora = (
            f"pierdes {abs(margen_actual):.1f}" if margen_actual < 0 else f"ganas {margen_actual:.1f}"
        )
        antes = (
            f"perdías {abs(margen_anterior):.1f}" if margen_anterior < 0 else f"ganabas {margen_anterior:.1f}"
        )
        alertas.append(
            {
                "severidad": "warning",
                "titulo": "Cada venta te deja menos ganancia",
                "detalle": (
                    f"De cada 100 que vendes, en {_periodo_texto(anterior)} {antes} después de pagar todos "
                    f"los costos y gastos; en {_periodo_texto(actual)} {ahora}."
                ),
                "en_simple": "Es el resultado de vender menos y, a la vez, gastar más en proporción a lo que vendes.",
                "grupos": _grupos(
                    _grupo(
                        "Ventas que más bajaron",
                        _cuentas_que_mas_cambiaron(actual, anterior, _es_cuenta_venta, 1, "baja", 2),
                    ),
                    _grupo(
                        "Gastos que más subieron",
                        _cuentas_que_mas_cambiaron(actual, anterior, _es_gasto_operativo, -1, "sube", 2),
                    ),
                ),
                "sugerencia": "Revisa las cuentas indicadas arriba: son las que más explican el cambio.",
            }
        )
    return alertas
