"""Construcción del Estado de Rendimiento Financiero (NIIF 18, versión simplificada).

Aplica la lógica simplificada de NIIF 18 a partir de las cuentas ya
clasificadas (CuentaContable.categoria_niif):

- Las 3 categorías obligatorias (Operación, Inversión, Financiación) siempre
  se presentan, aunque no tengan cuentas asociadas.
- Las 2 categorías restantes (Impuesto a las ganancias, Operaciones
  discontinuadas) solo se agregan si existen cuentas clasificadas en ellas.
- Los dos subtotales nuevos y obligatorios de NIIF 18 son "Resultado
  operativo" (cierre de la categoría Operación) y "Resultado antes de
  financiación e impuestos a las ganancias" (cierre acumulado de Operación +
  Inversión). Confirmado en ifrs.org: "requiring an entity to present two new
  defined subtotals ... operating profit and profit before financing and
  income taxes".
- No se mezclan partidas de distinta naturaleza: cada cuenta se presenta en
  su propia línea dentro de su categoría (sin agregación/desagregación).
- "Ganancia bruta" es un subtotal adicional (no obligatorio) dentro de
  Operación: ingresos de actividades ordinarias menos costo de ventas. Solo
  se presenta si se identifican cuentas de ambos tipos (cuentas_ventas.py).
"""
from cuentas_ventas import es_costo_ventas, es_venta
from models import CATEGORIAS_NIIF

OPERACION, INVERSION, FINANCIACION, IMPUESTO, DISCONTINUADAS = CATEGORIAS_NIIF


def construir_estado(cuentas):
    """cuentas: lista de CuentaContable ya clasificadas.
    Devuelve (filas, resumen) donde filas es la lista de líneas a renderizar
    y resumen trae los subtotales clave para el panel lateral."""
    por_categoria = {cat: [] for cat in CATEGORIAS_NIIF}
    for cuenta in cuentas:
        por_categoria.setdefault(cuenta.categoria_niif, []).append(cuenta)

    filas = []
    acumulado = 0.0

    # 1) Operación — categoría obligatoria
    filas.append({"tipo": "grupo", "texto": "01 Operación"})
    cuentas_operacion = por_categoria[OPERACION]
    ventas = [c for c in cuentas_operacion if es_venta(c.nombre)]
    costos_ventas = [c for c in cuentas_operacion if c not in ventas and es_costo_ventas(c.nombre)]
    ganancia_bruta = None
    if ventas and costos_ventas:
        # Ventas y costo de ventas van primero para presentar la Ganancia bruta
        # antes de los demás gastos de operación.
        ganancia_bruta = sum(c.importe for c in ventas + costos_ventas)
        resto = [c for c in cuentas_operacion if c not in ventas and c not in costos_ventas]
        cuentas_operacion = ventas + costos_ventas
    else:
        resto = []

    for c in cuentas_operacion:
        filas.append({"tipo": "detalle", "concepto": c.nombre, "valor": c.importe, "cuenta_id": c.id})
    if ganancia_bruta is not None:
        filas.append({
            "tipo": "subtotal", "concepto": "Ganancia bruta", "valor": ganancia_bruta, "adicional": True,
        })
        for c in resto:
            filas.append({"tipo": "detalle", "concepto": c.nombre, "valor": c.importe, "cuenta_id": c.id})
    acumulado += sum(c.importe for c in por_categoria[OPERACION])
    resultado_operativo = acumulado
    filas.append({
        "tipo": "resultado", "concepto": "Resultado operativo", "valor": resultado_operativo,
        "obligatorio": True,
    })

    # 2) Inversión — categoría obligatoria
    filas.append({"tipo": "grupo", "texto": "02 Inversión"})
    for c in por_categoria[INVERSION]:
        filas.append({"tipo": "detalle", "concepto": c.nombre, "valor": c.importe, "cuenta_id": c.id})
    acumulado += sum(c.importe for c in por_categoria[INVERSION])
    resultado_antes_financiacion_impuestos = acumulado
    filas.append({
        "tipo": "resultado",
        "concepto": "Resultado antes de financiación e impuestos a las ganancias",
        "valor": resultado_antes_financiacion_impuestos,
        "obligatorio": True,
    })

    # 3) Financiación — categoría obligatoria
    filas.append({"tipo": "grupo", "texto": "03 Financiación"})
    for c in por_categoria[FINANCIACION]:
        filas.append({"tipo": "detalle", "concepto": c.nombre, "valor": c.importe, "cuenta_id": c.id})
    acumulado += sum(c.importe for c in por_categoria[FINANCIACION])
    resultado_antes_impuestos = acumulado
    filas.append({"tipo": "subtotal", "concepto": "Resultado antes de impuestos", "valor": resultado_antes_impuestos})

    # 4) Impuesto a las ganancias — solo si hay cuentas de esta categoría
    cuentas_impuesto = por_categoria[IMPUESTO]
    cuentas_discontinuadas = por_categoria[DISCONTINUADAS]

    if cuentas_impuesto:
        filas.append({"tipo": "grupo", "texto": "04 Impuesto a las ganancias"})
        for c in cuentas_impuesto:
            filas.append({"tipo": "detalle", "concepto": c.nombre, "valor": c.importe, "cuenta_id": c.id})
        acumulado += sum(c.importe for c in cuentas_impuesto)

    if cuentas_impuesto or cuentas_discontinuadas:
        filas.append({
            "tipo": "subtotal", "concepto": "Resultado de operaciones continuadas", "valor": acumulado,
        })

    # 5) Operaciones discontinuadas — solo si hay cuentas de esta categoría
    if cuentas_discontinuadas:
        filas.append({"tipo": "grupo", "texto": "05 Operaciones discontinuadas"})
        for c in cuentas_discontinuadas:
            filas.append({"tipo": "detalle", "concepto": c.nombre, "valor": c.importe, "cuenta_id": c.id})
        acumulado += sum(c.importe for c in cuentas_discontinuadas)

    filas.append({"tipo": "final", "concepto": "Resultado del periodo", "valor": acumulado})

    ingresos_operacion = sum(c.importe for c in por_categoria[OPERACION] if c.importe > 0)
    margen = (acumulado / ingresos_operacion * 100) if ingresos_operacion else None

    resumen = {
        "ganancia_bruta": ganancia_bruta,
        "resultado_operativo": resultado_operativo,
        "resultado_antes_financiacion_impuestos": resultado_antes_financiacion_impuestos,
        "resultado_antes_impuestos": resultado_antes_impuestos,
        "resultado_periodo": acumulado,
        "margen": margen,
        "resumen_categorias": {cat: len(por_categoria[cat]) for cat in CATEGORIAS_NIIF},
    }
    return filas, resumen


def combinar_con_periodo_anterior(filas_actual, filas_anterior):
    """Agrega "valor_anterior" a cada fila de filas_actual buscando la misma
    fila (por concepto) en filas_anterior, para armar una comparación de
    periodos como la de un estado de resultados comparativo tradicional."""
    valores_anteriores = {
        fila["concepto"]: fila["valor"] for fila in filas_anterior if fila["tipo"] != "grupo"
    }

    filas_combinadas = []
    for fila in filas_actual:
        nueva = dict(fila)
        if fila["tipo"] != "grupo":
            nueva["valor_anterior"] = valores_anteriores.get(fila["concepto"])
        filas_combinadas.append(nueva)
    return filas_combinadas
