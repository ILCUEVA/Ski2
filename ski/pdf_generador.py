"""Generación del PDF del Estado de Rendimiento Financiero (NIIF 18, versión simplificada).

El formato sigue la presentación habitual de un estado de resultados NIIF:
encabezado con la entidad, el periodo y la moneda; cuentas agrupadas por
categoría con sus subtotales en negrita, y el resultado del periodo
destacado al final. Confirmado en ifrs.org para NIIF 18: "requiring an
entity to present two new defined subtotals in the statement of profit or
loss — operating profit and profit before financing and income taxes."
"""
import io
import re
import unicodedata
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

MORADO = colors.HexColor("#6d3df0")
GRIS = colors.HexColor("#6b7280")

_PATRON_CODIGO_INICIAL = re.compile(r"^[\d.\-\s]+(?=[A-Za-zÁÉÍÓÚÑÜáéíóúñü])")


def _formato_monto(valor):
    texto = f"{abs(valor):,.0f}".replace(",", ".")
    return f"({texto})" if valor < 0 else texto


def _solo_nombre_cuenta(texto):
    """Quita un eventual código inicial (ej. “4010110 - ”) para que el PDF
    muestre solo el nombre de la cuenta, sin el código contable."""
    return _PATRON_CODIGO_INICIAL.sub("", texto).strip()


def _normalizar(texto):
    texto = (texto or "").lower()
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )


def _coincide(concepto, palabras):
    nombre = _normalizar(concepto)
    return any(palabra in nombre for palabra in palabras)


def _detalles_por_categoria(filas_estado):
    categorias = {}
    categoria_actual = None
    for fila in filas_estado:
        if fila["tipo"] == "grupo":
            categoria_actual = fila["texto"]
            categorias[categoria_actual] = []
        elif fila["tipo"] == "detalle" and categoria_actual:
            categorias[categoria_actual].append(fila)
    return categorias


def _resumir_fila(concepto, cuentas, comparar, tipo="detalle", obligatorio=False):
    fila = {
        "tipo": tipo,
        "concepto": concepto,
        "valor": sum(cuenta["valor"] for cuenta in cuentas),
    }
    if comparar:
        fila["valor_anterior"] = sum(cuenta.get("valor_anterior") or 0 for cuenta in cuentas)
    if obligatorio:
        fila["obligatorio"] = True
    return fila


def _fila_de_origen(filas_estado, concepto_origen, concepto, comparar, tipo, fallback):
    origen = next(
        (
            fila
            for fila in filas_estado
            if fila.get("concepto") == concepto_origen and fila["tipo"] != "detalle"
        ),
        None,
    )
    fila = {"tipo": tipo, "concepto": concepto, "valor": origen["valor"] if origen else fallback}
    if comparar:
        fila["valor_anterior"] = (origen.get("valor_anterior") or 0) if origen else 0
    if origen and origen.get("obligatorio"):
        fila["obligatorio"] = True
    return fila


def _filas_por_funcion(filas_estado):
    comparar = any("valor_anterior" in fila for fila in filas_estado)
    categorias = _detalles_por_categoria(filas_estado)
    operacion = categorias.get("01 Operación", [])
    inversion = categorias.get("02 Inversión", [])
    financiacion = categorias.get("03 Financiación", [])
    impuestos = categorias.get("04 Impuesto a las ganancias", [])
    discontinuadas = categorias.get("05 Operaciones discontinuadas", [])
    filas = []

    ingresos = [
        cuenta
        for cuenta in operacion
        if cuenta["valor"] > 0
        and _coincide(
            cuenta["concepto"],
            ("venta", "ingreso ordinario", "actividades ordinarias", "prestacion de servicios"),
        )
    ]
    restantes = [cuenta for cuenta in operacion if cuenta not in ingresos]
    costos_venta = [
        cuenta
        for cuenta in restantes
        if _coincide(cuenta["concepto"], ("costo de venta", "costo venta"))
    ]
    restantes = [cuenta for cuenta in restantes if cuenta not in costos_venta]

    if ingresos:
        filas.append(_resumir_fila("Ingresos de actividades ordinarias", ingresos, comparar))
    if costos_venta:
        filas.append(_resumir_fila("Costo de ventas", costos_venta, comparar))
    if ingresos or costos_venta:
        filas.append(
            _resumir_fila(
                "Ganancia bruta",
                ingresos + costos_venta,
                comparar,
                tipo="subtotal",
            )
        )

    deterioros = [
        cuenta
        for cuenta in restantes
        if _coincide(cuenta["concepto"], ("deterioro", "perdida esperada", "castigo de cuentas por cobrar"))
    ]
    restantes = [cuenta for cuenta in restantes if cuenta not in deterioros]
    diferencias_cambio = [
        cuenta
        for cuenta in restantes
        if _coincide(cuenta["concepto"], ("diferencia de cambio", "diferencias de cambio"))
    ]
    restantes = [cuenta for cuenta in restantes if cuenta not in diferencias_cambio]
    reajustes = [
        cuenta
        for cuenta in restantes
        if _coincide(cuenta["concepto"], ("unidad de reajuste", "unidades de reajuste", "reajuste"))
    ]
    restantes = [cuenta for cuenta in restantes if cuenta not in reajustes]
    otras_ganancias = [
        cuenta
        for cuenta in restantes
        if cuenta["valor"] > 0
        or _coincide(cuenta["concepto"], ("otro ingreso", "otros ingresos", "otras ganancias", "otros gastos"))
    ]
    restantes = [cuenta for cuenta in restantes if cuenta not in otras_ganancias]

    if restantes:
        filas.append(_resumir_fila("Gastos de administración", restantes, comparar))
    if otras_ganancias:
        filas.append(_resumir_fila("Otras ganancias (pérdidas)", otras_ganancias, comparar))
    if deterioros:
        filas.append(_resumir_fila("Deterioro y pérdidas crediticias esperadas", deterioros, comparar))
    if diferencias_cambio:
        filas.append(_resumir_fila("Ganancias (pérdidas) de cambio", diferencias_cambio, comparar))
    if reajustes:
        filas.append(_resumir_fila("Resultados por unidades de reajuste", reajustes, comparar))

    resultado_operativo = _fila_de_origen(
        filas_estado,
        "Resultado operativo",
        "Ganancias (pérdidas) de actividades operacionales",
        comparar,
        "resultado",
        sum(cuenta["valor"] for cuenta in operacion),
    )
    resultado_operativo["obligatorio"] = True
    filas.append(resultado_operativo)

    relacionadas = [
        cuenta
        for cuenta in inversion
        if _coincide(cuenta["concepto"], ("asociada", "relacionada", "metodo de la participacion"))
    ]
    otras_inversiones = [cuenta for cuenta in inversion if cuenta not in relacionadas]
    if relacionadas:
        filas.append(
            _resumir_fila(
                "Ganancias (pérdidas) en empresas relacionadas",
                relacionadas,
                comparar,
            )
        )
    if otras_inversiones:
        filas.append(
            _resumir_fila("Otros ingresos y gastos de inversiones", otras_inversiones, comparar)
        )

    resultado_antes_financiacion = _fila_de_origen(
        filas_estado,
        "Resultado antes de financiación e impuestos a las ganancias",
        "Ganancias (pérdidas) antes de financiación e impuesto a la renta",
        comparar,
        "subtotal",
        sum(cuenta["valor"] for cuenta in operacion + inversion),
    )
    resultado_antes_financiacion["obligatorio"] = True
    filas.append(resultado_antes_financiacion)

    grupos_financiacion = [
        ("Intereses y gastos sobre pasivos por arrendamientos", ("arrendamiento", "leasing")),
        ("Intereses y costos por bonos emitidos", ("bono",)),
        ("Intereses y gastos por préstamos", ("prestamo",)),
        ("Resultados por unidades de reajuste de financiación", ("reajuste",)),
    ]
    restantes_financiacion = financiacion
    for concepto, palabras in grupos_financiacion:
        grupo = [
            cuenta
            for cuenta in restantes_financiacion
            if _coincide(cuenta["concepto"], palabras)
        ]
        restantes_financiacion = [
            cuenta for cuenta in restantes_financiacion if cuenta not in grupo
        ]
        if grupo:
            filas.append(_resumir_fila(concepto, grupo, comparar))
    if restantes_financiacion:
        filas.append(
            _resumir_fila("Otros costos financieros", restantes_financiacion, comparar)
        )

    resultado_antes_impuestos = _fila_de_origen(
        filas_estado,
        "Resultado antes de impuestos",
        "Ganancias (pérdidas) antes de impuesto",
        comparar,
        "subtotal",
        sum(cuenta["valor"] for cuenta in operacion + inversion + financiacion),
    )
    filas.append(resultado_antes_impuestos)

    impuestos_corrientes = [
        cuenta for cuenta in impuestos if _coincide(cuenta["concepto"], ("corriente",))
    ]
    impuestos_diferidos = [
        cuenta for cuenta in impuestos if _coincide(cuenta["concepto"], ("diferido",))
    ]
    otros_impuestos = [
        cuenta for cuenta in impuestos if cuenta not in impuestos_corrientes + impuestos_diferidos
    ]
    for concepto, grupo in (
        ("Gastos por impuestos corrientes", impuestos_corrientes),
        ("Ingreso (gasto) por impuestos diferidos", impuestos_diferidos),
        ("Otros impuestos a las ganancias", otros_impuestos),
    ):
        if grupo:
            filas.append(_resumir_fila(concepto, grupo, comparar))

    resultado_continuadas = _resumir_fila(
        "Ganancia (pérdida) procedente de actividades que continúan",
        operacion + inversion + financiacion + impuestos,
        comparar,
        tipo="subtotal",
    )
    filas.append(resultado_continuadas)

    if discontinuadas:
        filas.append(
            _resumir_fila(
                "Ganancia (pérdida) de operaciones discontinuadas",
                discontinuadas,
                comparar,
            )
        )
    filas.append(
        _fila_de_origen(
            filas_estado,
            "Resultado del periodo",
            "Ganancia (pérdida)",
            comparar,
            "final",
            sum(cuenta["valor"] for cuenta in operacion + inversion + financiacion + impuestos + discontinuadas),
        )
    )
    return filas


def generar_pdf_estado(empresa, balance, filas_estado, periodo_anterior=None, cuentas=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("titulo", parent=estilos["Heading1"], textColor=MORADO, spaceAfter=2)
    subtitulo = ParagraphStyle("subtitulo", parent=estilos["Normal"], textColor=GRIS, spaceAfter=2)
    celda = ParagraphStyle("celda", parent=estilos["Normal"], fontSize=9, leading=11)
    celda_negrita = ParagraphStyle("celda_negrita", parent=celda, fontName="Helvetica-Bold")
    celda_blanca = ParagraphStyle("celda_blanca", parent=celda_negrita, textColor=colors.white)

    periodo = balance.periodo if balance else empresa.anio_vigente
    comparar = any("valor_anterior" in fila for fila in filas_estado)

    subtitulo_cifras = f"Cifras expresadas en {empresa.moneda} · Borrador, sujeto a revisión contable"
    if comparar:
        subtitulo_cifras += f" · Comparado con el periodo {periodo_anterior}"

    elementos = [
        Paragraph(empresa.nombre, titulo),
        Paragraph("Estado de Resultados por Función (NIIF 18 · versión simplificada)", subtitulo),
        Paragraph(f"Por el periodo terminado el 31 de diciembre de {periodo}", subtitulo),
        Paragraph(subtitulo_cifras, subtitulo),
        Spacer(1, 0.6 * cm),
    ]

    if comparar:
        datos = [["Estado de Resultados", str(periodo), str(periodo_anterior)]]
        col_widths = [9 * cm, 4 * cm, 4 * cm]
    else:
        datos = [["Estado de Resultados", str(periodo)]]
        col_widths = [12 * cm, 5 * cm]

    ultima_col = len(datos[0]) - 1
    estilos_tabla = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), MORADO),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]

    def _valor_anterior(fila):
        valor = fila.get("valor_anterior")
        return _formato_monto(valor) if valor is not None else "—"

    ventas_afectas = []
    costos_ventas_afectas = []
    categoria_actual = None
    for fila in filas_estado:
        if fila["tipo"] == "grupo":
            categoria_actual = fila["texto"]
            continue
        if categoria_actual != "01 Operación" or fila["tipo"] != "detalle":
            continue
        nombre = _normalizar(fila["concepto"])
        if "venta" in nombre and "afecta" in nombre:
            if "costo" in nombre:
                costos_ventas_afectas.append(fila)
            else:
                ventas_afectas.append(fila)

    cuentas_ganancia_bruta = ventas_afectas + costos_ventas_afectas
    ids_cuentas_ganancia_bruta = {id(fila) for fila in cuentas_ganancia_bruta}
    filas_pdf = []
    for fila in filas_estado:
        filas_pdf.append(fila)
        if fila["tipo"] == "grupo" and fila["texto"] == "01 Operación" and cuentas_ganancia_bruta:
            filas_pdf.extend(cuentas_ganancia_bruta)
            anteriores = [fila.get("valor_anterior") for fila in cuentas_ganancia_bruta]
            fila_ganancia_bruta = {
                "tipo": "subtotal",
                "concepto": "Ganancia bruta",
                "valor": sum(fila["valor"] for fila in cuentas_ganancia_bruta),
            }
            if comparar:
                fila_ganancia_bruta["valor_anterior"] = (
                    sum(valor for valor in anteriores if valor is not None)
                    if any(valor is not None for valor in anteriores)
                    else None
                )
            filas_pdf.append(fila_ganancia_bruta)
        elif fila["tipo"] == "detalle" and id(fila) in ids_cuentas_ganancia_bruta:
            filas_pdf.pop()

    rotulos_estructurales = {
        "Resultado operativo": "Ganancias (pérdidas) de actividades operacionales",
        "Resultado antes de financiación e impuestos a las ganancias": (
            "Ganancias (pérdidas) antes de financiación e impuesto a la renta"
        ),
        "Resultado antes de impuestos": "Ganancias (pérdidas) antes de impuesto",
        "Resultado de operaciones continuadas": (
            "Ganancia (pérdida) procedente de actividades que continúan"
        ),
        "Resultado del periodo": "Ganancia (pérdida)",
    }

    for fila in filas_pdf:
        if fila["tipo"] == "grupo":
            continue

        fila_idx = len(datos)
        if fila["tipo"] == "final":
            concepto = rotulos_estructurales.get(fila["concepto"], fila["concepto"])
            fila_datos = [Paragraph(escape(concepto), celda_blanca), _formato_monto(fila["valor"])]
            if comparar:
                fila_datos.append(_valor_anterior(fila))
            datos.append(fila_datos)
            estilos_tabla += [
                ("BACKGROUND", (0, fila_idx), (-1, fila_idx), MORADO),
                ("TEXTCOLOR", (0, fila_idx), (-1, fila_idx), colors.white),
                ("FONTNAME", (0, fila_idx), (-1, fila_idx), "Helvetica-Bold"),
            ]
        else:
            concepto = rotulos_estructurales.get(fila["concepto"], fila["concepto"])
            concepto = escape(_solo_nombre_cuenta(concepto))
            estilo_concepto = celda_negrita if fila["tipo"] in ("subtotal", "resultado") else celda
            fila_datos = [Paragraph(concepto, estilo_concepto), _formato_monto(fila["valor"])]
            if comparar:
                fila_datos.append(_valor_anterior(fila))
            datos.append(fila_datos)
            if fila["tipo"] in ("subtotal", "resultado"):
                estilos_tabla += [
                    ("FONTNAME", (0, fila_idx), (-1, fila_idx), "Helvetica-Bold"),
                    ("LINEABOVE", (0, fila_idx), (-1, fila_idx), 0.5, GRIS),
                ]

    tabla = Table(datos, colWidths=col_widths)
    tabla.setStyle(TableStyle(estilos_tabla))
    elementos.append(tabla)
    elementos.append(Spacer(1, 0.8 * cm))

    nota = (
        "Versión simplificada de NIIF 18. Las cuentas se muestran según la clasificación confirmada "
        "en el paso 3, con sus nombres e importes originales. Los subtotales "
        "\u201cResultado operativo\u201d y \u201cResultado antes de financiación e impuestos a las ganancias\u201d "
        "son obligatorios según NIIF 18. El desglose de gastos por naturaleza y este borrador requieren "
        "revisión contable."
    )
    if periodo_anterior and not comparar:
        nota += f" No se encontraron cuentas revisadas del periodo {periodo_anterior} para comparar."
    nota_estilo = ParagraphStyle("nota", parent=estilos["Normal"], fontSize=7.5, textColor=GRIS)
    elementos.append(Paragraph(nota, nota_estilo))
    elementos.append(Spacer(1, 0.3 * cm))
    elementos.append(
        Paragraph(f"Generado por Balancea el {date.today().strftime('%d-%m-%Y')}.", nota_estilo)
    )

    doc.build(elementos)
    buffer.seek(0)
    return buffer
