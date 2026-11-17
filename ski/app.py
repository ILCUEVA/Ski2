import os
from datetime import datetime
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, send_file, send_from_directory, session, url_for
from sqlalchemy import inspect, text
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from models import CATEGORIAS_NIIF, RUBROS, RUBROS_ICONOS, Balance, CompraPackInforme, CuentaContable, Empresa, InformeEstadoResultados, MEDIOS_PAGO, MovimientoContable, PACKS, PACKS_CON_MPM, Pago, Usuario, db
from seed import seed_demo_data
from currencies import MONEDA_BASE, MONEDAS
from importador import ImportadorInvalido, buscar_movimientos, leer_cuentas_resultado, leer_movimientos_libro_mayor
from clasificador import clasificar_cuenta, motivo_clasificacion
from estado_financiero import combinar_con_periodo_anterior, construir_estado
from pdf_generador import generar_pdf_estado
from progreso import calcular_progreso, limpiar_balances_expirados
from mpm_sugeridas import calcular_mpm_sugeridas, mpm_sugeridas_por_rubro
from toma_decisiones import calcular_alertas, calcular_comparativos, calcular_tendencias, preparar_grafico_margenes

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")


def formato_monto(valor):
    return f"{valor:,.0f}".replace(",", ".")


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    # en un despliegue real definir SECRET_KEY como variable de entorno
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-balancea-local-key")

    os.makedirs(app.instance_path, exist_ok=True)
    db_path = os.path.join(app.instance_path, "balancea.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    informes_dir = os.path.join(app.instance_path, "informes")
    os.makedirs(informes_dir, exist_ok=True)
    app.config["INFORMES_DIR"] = informes_dir

    db.init_app(app)
    app.jinja_env.filters["monto"] = formato_monto

    with app.app_context():
        db.create_all()
        compra_columns = {
            columna["name"]
            for columna in inspect(db.engine).get_columns("compras_packs_informes")
        }
        if "medio_pago" not in compra_columns:
            with db.engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE compras_packs_informes ADD COLUMN medio_pago VARCHAR(50)")
                )
        seed_demo_data(db)

    register_routes(app)
    return app


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("usuario_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def register_routes(app):
    def empresa_actual():
        usuario = db.session.get(Usuario, session["usuario_id"])
        empresa = usuario.empresa
        limpiar_balances_expirados(empresa, db)
        return empresa

    def balance_actual(empresa):
        return (
            Balance.query.filter_by(empresa_id=empresa.id)
            .order_by(Balance.id.desc())
            .populate_existing()
            .first()
        )

    def cuentas_balance(balance):
        if not balance:
            return []
        return (
            CuentaContable.query.filter_by(balance_id=balance.id)
            .order_by(CuentaContable.codigo)
            .populate_existing()
            .all()
        )

    def balance_anterior_revisado(empresa, balance):
        try:
            periodo = str(int(balance.periodo) - 1)
        except (AttributeError, TypeError, ValueError):
            return None, []
        balance_anterior = (
            Balance.query.filter_by(empresa_id=empresa.id, periodo=periodo)
            .order_by(Balance.id.desc())
            .populate_existing()
            .first()
        )
        cuentas_anteriores = [
            cuenta for cuenta in cuentas_balance(balance_anterior) if cuenta.revisado
        ]
        return (balance_anterior, cuentas_anteriores) if cuentas_anteriores else (None, [])

    def compras_pack_empresa(empresa):
        return (
            CompraPackInforme.query.filter_by(empresa_id=empresa.id)
            .order_by(CompraPackInforme.id.asc())
            .all()
        )

    def informes_pack_disponibles(empresa):
        return sum(
            max(0, compra.informes_incluidos - compra.informes_usados)
            for compra in compras_pack_empresa(empresa)
        )

    def resumen_pack_empresa(empresa):
        compras = compras_pack_empresa(empresa)
        if not compras:
            return None
        compra = next(
            (
                pack
                for pack in compras
                if pack.informes_usados < pack.informes_incluidos
            ),
            compras[-1],
        )
        return {
            "nombre": compra.nombre_pack,
            "incluidos": compra.informes_incluidos,
            "usados": compra.informes_usados,
            "restantes": max(0, compra.informes_incluidos - compra.informes_usados),
        }

    def siguiente_compra_pack(empresa):
        return next(
            (
                compra
                for compra in compras_pack_empresa(empresa)
                if compra.informes_usados < compra.informes_incluidos
            ),
            None,
        )

    @app.context_processor
    def inject_usuario():
        usuario = None
        resumen_pack = None
        if session.get("usuario_id"):
            usuario = db.session.get(Usuario, session["usuario_id"])
            if usuario:
                resumen_pack = resumen_pack_empresa(usuario.empresa)
        return dict(usuario_actual=usuario, resumen_pack=resumen_pack)

    @app.route("/")
    def index():
        if session.get("usuario_id"):
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("usuario_id"):
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            correo = request.form.get("correo", "").strip().lower()
            password = request.form.get("password", "")
            usuario = Usuario.query.filter_by(correo=correo).first()
            if usuario and check_password_hash(usuario.password_hash, password):
                session["usuario_id"] = usuario.id
                return redirect(url_for("dashboard"))
            flash("Correo o contraseña incorrectos.", "danger")
            return redirect(url_for("login"))
        return render_template("auth/login.html")

    @app.route("/registro", methods=["GET", "POST"])
    def registro():
        if session.get("usuario_id"):
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            nombre_empresa = request.form.get("nombre_empresa", "").strip()
            rubro_seleccionado = request.form.get("rubro", "")
            if rubro_seleccionado == "Otro":
                rubro = request.form.get("rubro_otro", "").strip()
                if not rubro or len(rubro) > 50:
                    flash("Escribe un rubro de hasta 50 caracteres.", "danger")
                    return redirect(url_for("registro"))
            elif rubro_seleccionado in RUBROS:
                rubro = rubro_seleccionado
            else:
                flash("Selecciona el rubro de tu empresa.", "danger")
                return redirect(url_for("registro"))
            correo = request.form.get("correo", "").strip().lower()
            password = request.form.get("password", "")

            if not nombre_empresa or not correo or not password:
                flash("Completa todos los campos obligatorios.", "danger")
                return redirect(url_for("registro"))
            elif Usuario.query.filter_by(correo=correo).first():
                flash("Ya existe una cuenta con ese correo.", "danger")
                return redirect(url_for("registro"))
            else:
                empresa = Empresa(nombre=nombre_empresa, rubro=rubro)
                db.session.add(empresa)
                db.session.flush()
                usuario = Usuario(
                    nombre=nombre_empresa,
                    correo=correo,
                    password_hash=generate_password_hash(password),
                    empresa_id=empresa.id,
                )
                db.session.add(usuario)
                db.session.commit()
                session["usuario_id"] = usuario.id
                return redirect(url_for("dashboard"))
        return render_template("auth/register.html", rubros=RUBROS, rubros_iconos=RUBROS_ICONOS)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        empresa = empresa_actual()
        balances = empresa.balances
        balance_actual = balances[0] if balances else None
        progresos = {b.id: calcular_progreso(b) for b in balances}
        return render_template(
            "dashboard.html",
            empresa=empresa,
            balances=balances,
            balance_actual=balance_actual,
            progresos=progresos,
        )

    @app.route("/subir-balance", methods=["GET", "POST"])
    @login_required
    def subir_balance():
        empresa = empresa_actual()
        moneda_actual = empresa.moneda if empresa and empresa.moneda else MONEDA_BASE

        if request.method == "POST":
            balance_file = request.files.get("balance_file")
            libro_mayor_file = request.files.get("libro_mayor_file")
            periodo = request.form.get("periodo", str(empresa.anio_vigente))
            moneda_sel = request.form.get("moneda", moneda_actual)

            if not balance_file or not balance_file.filename:
                flash("Debes adjuntar el archivo de balance.", "danger")
                return redirect(url_for("subir_balance"))
            else:
                try:
                    cuentas_resultado = leer_cuentas_resultado(balance_file)
                    movimientos_por_cuenta = {}
                    if libro_mayor_file and libro_mayor_file.filename:
                        movimientos_por_cuenta = leer_movimientos_libro_mayor(libro_mayor_file)
                except ImportadorInvalido as exc:
                    flash(str(exc), "danger")
                    return redirect(url_for("subir_balance"))
                else:
                    balance = Balance(
                        empresa_id=empresa.id,
                        archivo_nombre=secure_filename(balance_file.filename),
                        archivo_libro_mayor=(
                            secure_filename(libro_mayor_file.filename)
                            if libro_mayor_file and libro_mayor_file.filename
                            else None
                        ),
                        periodo=periodo,
                        estado="Borrador",
                    )
                    db.session.add(balance)
                    db.session.flush()

                    for indice, cuenta in enumerate(cuentas_resultado, start=1):
                        cuenta_contable = CuentaContable(
                            balance_id=balance.id,
                            codigo=f"{indice:03d}",
                            nombre=cuenta["nombre"],
                            importe=cuenta["importe"],
                            categoria_niif=clasificar_cuenta(cuenta["nombre"]),
                            revisado=False,
                        )
                        db.session.add(cuenta_contable)
                        db.session.flush()

                        movimientos = buscar_movimientos(movimientos_por_cuenta, cuenta["nombre"])
                        for mov in movimientos:
                            db.session.add(MovimientoContable(cuenta_id=cuenta_contable.id, **mov))

                    empresa.moneda = moneda_sel
                    db.session.commit()
                    flash(
                        f"Se clasificaron {len(cuentas_resultado)} cuentas automáticamente según NIIF 18. "
                        "Revisa y confirma cada una antes de generar el informe.",
                        "success",
                    )
                    return redirect(url_for("clasificacion"))

        return render_template(
            "subir_balance.html", empresa=empresa, monedas=MONEDAS, moneda_actual=moneda_actual
        )

    @app.route("/plantillas/balance")
    @login_required
    def descargar_plantilla_balance():
        return send_from_directory(DATA_DIR, "Importador_balance.xlsx", as_attachment=True)

    @app.route("/plantillas/libro-mayor")
    @login_required
    def descargar_plantilla_libro_mayor():
        return send_from_directory(DATA_DIR, "Importador_libro_mayor.xlsx", as_attachment=True)

    @app.route("/clasificacion")
    @login_required
    def clasificacion():
        empresa = empresa_actual()
        balance = balance_actual(empresa)
        cuentas = cuentas_balance(balance)
        revisadas = sum(1 for c in cuentas if c.revisado)
        total = len(cuentas)
        pendientes = total - revisadas
        porcentaje = int((revisadas / total) * 100) if total else 0
        resumen_categorias = {
            cat: sum(1 for c in cuentas if c.categoria_niif == cat) for cat in CATEGORIAS_NIIF
        }
        cuenta_en_revision = next((c for c in cuentas if not c.revisado), None)
        criterios = {c.id: motivo_clasificacion(c.nombre, c.observacion) for c in cuentas}
        return render_template(
            "clasificacion.html",
            empresa=empresa,
            balance=balance,
            cuentas=cuentas,
            revisadas=revisadas,
            pendientes=pendientes,
            total=total,
            porcentaje=porcentaje,
            resumen_categorias=resumen_categorias,
            categorias=CATEGORIAS_NIIF,
            cuenta_en_revision=cuenta_en_revision,
            criterios=criterios,
        )

    @app.route("/estado-resultados/exportar", methods=["POST"])
    @login_required
    def exportar_estado_resultados():
        empresa = empresa_actual()
        balance = balance_actual(empresa)
        cuentas = [cuenta for cuenta in cuentas_balance(balance) if cuenta.revisado]
        if not balance or not cuentas:
            flash("Aún no hay cuentas revisadas para generar el informe.", "danger")
            return redirect(url_for("estado_resultados"))

        compra_pack = siguiente_compra_pack(empresa)
        if not compra_pack:
            flash("No tienes informes disponibles. Compra un pack para generar el PDF.", "warning")
            return redirect(url_for("packs"))

        periodo_modo = request.form.get("periodo_modo", "actual")
        if periodo_modo not in {"actual", "comparar"}:
            flash("Selecciona un periodo válido para el informe.", "danger")
            return redirect(url_for("estado_resultados"))

        filas_estado, _ = construir_estado(cuentas)
        periodo_pdf = None
        if periodo_modo == "comparar":
            balance_anterior, cuentas_anteriores = balance_anterior_revisado(empresa, balance)
            if not balance_anterior:
                flash("No hay un balance anterior con cuentas revisadas para comparar.", "warning")
                return redirect(url_for("estado_resultados"))
            periodo_pdf = balance_anterior.periodo
            filas_anterior, _ = construir_estado(cuentas_anteriores)
            filas_estado = combinar_con_periodo_anterior(filas_estado, filas_anterior)

        pdf_buffer = generar_pdf_estado(
            empresa, balance, filas_estado, periodo_pdf, cuentas=cuentas
        )

        nombre_empresa = secure_filename(empresa.nombre) or "empresa"
        marca_tiempo = datetime.utcnow().strftime("%Y%m%d-%H%M%S%f")
        nombre_archivo = (
            f"Estado_Rendimiento_Financiero_{nombre_empresa}_{balance.periodo}_{marca_tiempo}.pdf"
        )

        ruta_guardada = os.path.join(app.config["INFORMES_DIR"], nombre_archivo)
        with open(ruta_guardada, "wb") as archivo_guardado:
            archivo_guardado.write(pdf_buffer.getvalue())

        db.session.add(
            InformeEstadoResultados(
                balance_id=balance.id, archivo_nombre=nombre_archivo, periodo=balance.periodo
            )
        )
        compra_pack.informes_usados += 1
        db.session.commit()

        pdf_buffer.seek(0)
        return send_file(
            pdf_buffer, mimetype="application/pdf", as_attachment=True, download_name=nombre_archivo
        )

    @app.route("/mis-documentos/informes/<int:informe_id>")
    @login_required
    def descargar_informe(informe_id):
        empresa = empresa_actual()
        informe = db.session.get(InformeEstadoResultados, informe_id)
        if not informe or informe.balance.empresa_id != empresa.id:
            flash("Informe no encontrado.", "danger")
            return redirect(url_for("mis_documentos"))
        return send_from_directory(app.config["INFORMES_DIR"], informe.archivo_nombre, as_attachment=True)

    @app.route("/mis-documentos/informes/<int:informe_id>/eliminar", methods=["POST"])
    @login_required
    def eliminar_informe(informe_id):
        empresa = empresa_actual()
        informe = db.session.get(InformeEstadoResultados, informe_id)
        if not informe or informe.balance.empresa_id != empresa.id:
            flash("Informe no encontrado.", "danger")
            return redirect(url_for("mis_documentos"))

        ruta = os.path.join(app.config["INFORMES_DIR"], informe.archivo_nombre)
        if os.path.exists(ruta):
            os.remove(ruta)
        db.session.delete(informe)
        db.session.commit()
        flash("Informe eliminado.", "success")
        return redirect(url_for("mis_documentos"))

    @app.route("/mis-documentos/balances/<int:balance_id>/eliminar", methods=["POST"])
    @login_required
    def eliminar_balance(balance_id):
        empresa = empresa_actual()
        balance = db.session.get(Balance, balance_id)
        if not balance or balance.empresa_id != empresa.id:
            flash("Balance no encontrado.", "danger")
            return redirect(url_for("mis_documentos"))

        for informe in list(balance.informes):
            ruta = os.path.join(app.config["INFORMES_DIR"], informe.archivo_nombre)
            if os.path.exists(ruta):
                os.remove(ruta)
            db.session.delete(informe)

        for cuenta in list(balance.cuentas):
            for movimiento in list(cuenta.movimientos):
                db.session.delete(movimiento)
            db.session.delete(cuenta)

        for pago in list(balance.pagos):
            db.session.delete(pago)

        db.session.delete(balance)
        db.session.commit()
        flash("Balance eliminado junto con su libro mayor e informes asociados.", "success")
        return redirect(url_for("mis_documentos"))

    @app.route("/mis-documentos/eliminar-todo", methods=["POST"])
    @login_required
    def eliminar_todos_documentos():
        empresa = empresa_actual()

        for balance in list(empresa.balances):
            for informe in list(balance.informes):
                ruta = os.path.join(app.config["INFORMES_DIR"], informe.archivo_nombre)
                if os.path.exists(ruta):
                    os.remove(ruta)
                db.session.delete(informe)

            for cuenta in list(balance.cuentas):
                for movimiento in list(cuenta.movimientos):
                    db.session.delete(movimiento)
                db.session.delete(cuenta)

            for pago in list(balance.pagos):
                db.session.delete(pago)

            db.session.delete(balance)

        db.session.commit()
        flash("Se eliminó todo el historial de documentos (balances, libros mayores, informes y pagos).", "success")
        return redirect(url_for("mis_documentos"))

    @app.route("/cuentas/<int:cuenta_id>/movimientos")
    @login_required
    def movimientos_cuenta(cuenta_id):
        empresa = empresa_actual()
        cuenta = db.session.get(CuentaContable, cuenta_id)
        if not cuenta or cuenta.balance.empresa_id != empresa.id:
            return "Cuenta no encontrada.", 404
        return render_template("_movimientos_cuenta.html", cuenta=cuenta, movimientos=cuenta.movimientos)

    @app.route("/clasificacion/confirmar/<int:cuenta_id>", methods=["POST"])
    @login_required
    def confirmar_cuenta(cuenta_id):
        empresa = empresa_actual()
        cuenta = db.session.get(CuentaContable, cuenta_id)
        if not cuenta or cuenta.balance.empresa_id != empresa.id:
            flash("Cuenta no encontrada.", "danger")
            return redirect(url_for("clasificacion"))

        categoria = request.form.get("categoria", cuenta.categoria_niif)
        if categoria in CATEGORIAS_NIIF:
            cuenta.categoria_niif = categoria
        cuenta.revisado = True
        db.session.commit()
        return redirect(url_for("clasificacion", _anchor=f"cuenta-{cuenta_id}"))

    @app.route("/clasificacion/confirmar-todas", methods=["POST"])
    @login_required
    def confirmar_todas_cuentas():
        empresa = empresa_actual()
        balance = balance_actual(empresa)
        if not balance:
            flash("No hay cuentas para revisar.", "info")
            return redirect(url_for("clasificacion"))

        pendientes = [cuenta for cuenta in cuentas_balance(balance) if not cuenta.revisado]
        for cuenta in pendientes:
            cuenta.revisado = True
        db.session.commit()
        flash(f"Se confirmaron {len(pendientes)} cuentas con sus categorías actuales.", "success")
        return redirect(url_for("clasificacion"))

    @app.route("/clasificacion/observacion/<int:cuenta_id>", methods=["POST"])
    @login_required
    def actualizar_observacion(cuenta_id):
        empresa = empresa_actual()
        cuenta = db.session.get(CuentaContable, cuenta_id)
        if not cuenta or cuenta.balance.empresa_id != empresa.id:
            flash("Cuenta no encontrada.", "danger")
            return redirect(url_for("clasificacion"))

        observacion = request.form.get("observacion", "").strip()
        cuenta.observacion = observacion or None
        categoria_anterior = cuenta.categoria_niif
        cuenta.categoria_niif = clasificar_cuenta(cuenta.nombre, observacion)
        if cuenta.categoria_niif != categoria_anterior:
            cuenta.revisado = False
            flash(
                f'Según tu observación, "{cuenta.nombre}" se reasignó de {categoria_anterior} a '
                f"{cuenta.categoria_niif}. Revísala y confírmala nuevamente.",
                "success",
            )
        else:
            flash("Observación guardada. La categoría sugerida no cambió.", "info")
        db.session.commit()
        return redirect(url_for("clasificacion", _anchor=f"cuenta-{cuenta_id}"))

    @app.route("/estado-resultados")
    @login_required
    def estado_resultados():
        empresa = empresa_actual()
        balance = balance_actual(empresa)
        cuentas = [cuenta for cuenta in cuentas_balance(balance) if cuenta.revisado]
        filas_estado, resumen = construir_estado(cuentas)
        balance_anterior, _ = balance_anterior_revisado(empresa, balance)
        compra_pack = siguiente_compra_pack(empresa)
        return render_template(
            "estado_resultados.html",
            empresa=empresa,
            balance=balance,
            cuentas=cuentas,
            informes_disponibles=informes_pack_disponibles(empresa),
            pack_actual=compra_pack.nombre_pack if compra_pack else None,
            balance_anterior=balance_anterior,
            filas_estado=filas_estado,
            resumen=resumen,
            categorias=CATEGORIAS_NIIF,
        )

    @app.route("/mpm")
    @login_required
    def mpm():
        empresa = empresa_actual()
        nombres_sugeridos = mpm_sugeridas_por_rubro(empresa.rubro)

        if empresa.pack_actual not in PACKS_CON_MPM:
            return render_template(
                "mpm.html", empresa=empresa, acceso_habilitado=False, nombres_sugeridos=nombres_sugeridos
            )

        balance = empresa.balances[0] if empresa.balances else None
        cuentas = balance.cuentas if balance else []
        mpm_sugeridas = []
        if balance and cuentas:
            _, resumen = construir_estado(cuentas)
            mpm_sugeridas = calcular_mpm_sugeridas(cuentas, resumen, empresa.rubro)
        return render_template(
            "mpm.html",
            empresa=empresa,
            acceso_habilitado=True,
            balance=balance,
            mpm_sugeridas=mpm_sugeridas,
            nombres_sugeridos=nombres_sugeridos,
        )

    @app.route("/toma-decisiones")
    @login_required
    def toma_decisiones():
        empresa = empresa_actual()
        tiene_datos = any(b.informes for b in empresa.balances)
        tendencias = calcular_tendencias(empresa) if tiene_datos else []
        grafico_margenes = preparar_grafico_margenes(tendencias)
        comparativos = calcular_comparativos(empresa) if tiene_datos else None
        alertas = calcular_alertas(empresa) if tiene_datos else []
        return render_template(
            "toma_decisiones.html",
            empresa=empresa,
            acceso_habilitado=True,
            tiene_datos=tiene_datos,
            tendencias=tendencias,
            grafico_margenes=grafico_margenes,
            comparativos=comparativos,
            alertas=alertas,
        )

    @app.route("/packs")
    @login_required
    def packs():
        empresa = empresa_actual()
        compras = compras_pack_empresa(empresa)
        compra_actual = siguiente_compra_pack(empresa)
        return_to_estado = request.args.get("return_to") == "estado_resultados"
        balance = balance_actual(empresa)
        hay_cuentas_revisadas = any(cuenta.revisado for cuenta in cuentas_balance(balance))
        return render_template(
            "packs.html",
            empresa=empresa,
            packs=PACKS,
            pack_actual=compra_actual.nombre_pack if compra_actual else None,
            informes_disponibles=informes_pack_disponibles(empresa),
            compras=compras,
            medios_pago=MEDIOS_PAGO,
            return_to_estado=return_to_estado,
            hay_cuentas_revisadas=hay_cuentas_revisadas,
        )

    @app.route("/packs/seleccionar", methods=["POST"])
    @login_required
    def seleccionar_pack():
        empresa = empresa_actual()
        pack = request.form.get("pack")
        medio_pago = request.form.get("medio_pago")
        return_to_estado = request.form.get("return_to") == "estado_resultados"
        if informes_pack_disponibles(empresa) > 0:
            flash("Debes usar todos los informes disponibles antes de comprar otro pack.", "warning")
        elif pack not in PACKS:
            flash("Selecciona un pack válido.", "danger")
        elif medio_pago not in MEDIOS_PAGO:
            flash("Selecciona un medio de pago válido.", "danger")
        else:
            detalle = PACKS[pack]
            db.session.add(
                CompraPackInforme(
                    empresa_id=empresa.id,
                    nombre_pack=pack,
                    informes_incluidos=detalle["informes"],
                    precio=detalle["precio"],
                    medio_pago=medio_pago,
                )
            )
            empresa.pack_actual = pack
            db.session.commit()
            flash(
                f"Pago simulado aprobado. Pack {pack} activado por ${detalle['precio']:,} CLP "
                f"con {detalle['informes']} informe{'s' if detalle['informes'] != 1 else ''} disponible{'s' if detalle['informes'] != 1 else ''}.",
                "success",
            )
        if return_to_estado:
            return redirect(url_for("estado_resultados"))
        return redirect(url_for("packs"))

    @app.route("/mis-documentos")
    @login_required
    def mis_documentos():
        empresa = empresa_actual()
        informes = (
            InformeEstadoResultados.query.join(Balance)
            .filter(Balance.empresa_id == empresa.id)
            .order_by(InformeEstadoResultados.fecha_generacion.desc())
            .all()
        )
        pagos = (
            Pago.query.join(Balance)
            .filter(Balance.empresa_id == empresa.id)
            .order_by(Pago.fecha_pago.desc())
            .all()
        )
        historial_pagos = [
            {
                "monto": compra.precio,
                "medio_pago": compra.medio_pago or "No registrado",
                "concepto": f"Pack {compra.nombre_pack} · {compra.informes_incluidos} informe{'s' if compra.informes_incluidos != 1 else ''}",
                "periodo": "—",
                "fecha": compra.fecha_compra,
            }
            for compra in compras_pack_empresa(empresa)
        ]
        historial_pagos.extend(
            {
                "monto": pago.monto,
                "medio_pago": pago.medio_pago,
                "concepto": "Estado de Rendimiento Financiero",
                "periodo": pago.balance.periodo,
                "fecha": pago.fecha_pago,
            }
            for pago in pagos
        )
        historial_pagos.sort(
            key=lambda pago: pago["fecha"] or datetime.min,
            reverse=True,
        )
        return render_template(
            "mis_documentos.html",
            empresa=empresa,
            balances=empresa.balances,
            informes=informes,
            pagos=pagos,
            historial_pagos=historial_pagos,
        )

    @app.route("/configuracion", methods=["GET", "POST"])
    @login_required
    def configuracion():
        empresa = empresa_actual()
        if request.method == "POST":
            nombre = request.form.get("nombre", "").strip()
            rubro_seleccionado = request.form.get("rubro", "")
            if rubro_seleccionado == "Otro":
                rubro = request.form.get("rubro_otro", "").strip()
                if not rubro or len(rubro) > 50:
                    flash("Escribe un rubro de hasta 50 caracteres.", "danger")
                    return redirect(url_for("configuracion"))
            elif rubro_seleccionado in RUBROS:
                rubro = rubro_seleccionado
            else:
                flash("Selecciona el rubro de tu empresa.", "danger")
                return redirect(url_for("configuracion"))
            moneda = request.form.get("moneda", empresa.moneda)

            if not nombre:
                flash("El nombre de la empresa no puede quedar vacío.", "danger")
                return redirect(url_for("configuracion"))

            empresa.nombre = nombre
            empresa.rubro = rubro
            if moneda in {m["codigo"] for m in MONEDAS}:
                empresa.moneda = moneda
            db.session.commit()
            flash("Datos de la empresa actualizados.", "success")
            return redirect(url_for("configuracion"))

        return render_template(
            "configuracion.html", empresa=empresa, rubros=RUBROS, monedas=MONEDAS, rubros_iconos=RUBROS_ICONOS
        )

    @app.route("/manual-usuario")
    @login_required
    def manual_usuario():
        empresa = empresa_actual()
        return render_template("manual_usuario.html", empresa=empresa)


app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)
