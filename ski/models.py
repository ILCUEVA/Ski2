from datetime import date, datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

RUBROS = [
    "Finanzas",
    "Constructoras",
    "Comercial",
    "Servicios profesionales",
    "Restaurantes y cafés",
    "Manufactura",
    "Tecnología",
    "Transporte y logística",
    "Farmacia",
]

RUBROS_ICONOS = {
    "Finanzas": "bi-cash-coin",
    "Constructoras": "bi-building",
    "Comercial": "bi-shop",
    "Servicios profesionales": "bi-briefcase",
    "Restaurantes y cafés": "bi-cup-hot",
    "Manufactura": "bi-gear",
    "Tecnología": "bi-cpu",
    "Transporte y logística": "bi-truck",
    "Farmacia": "bi-capsule",
}

CATEGORIAS_NIIF = [
    "Operación",
    "Inversión",
    "Financiación",
    "Impuestos a las ganancias",
    "Operaciones discontinuadas",
]

PACKS = {
    "Express": {"informes": 1, "precio": 12990},
    "Plus": {"informes": 3, "precio": 35970},
    "Pro": {"informes": 5, "precio": 49950},
}
PACKS_CON_MPM = set()


class Empresa(db.Model):
    __tablename__ = "empresas"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    tipo = db.Column(db.String(50), default="PYME")
    pais = db.Column(db.String(80), default="Chile")
    rubro = db.Column(db.String(50), nullable=False)
    moneda = db.Column(db.String(10), default="CLP")
    anio_vigente = db.Column(db.Integer, default=date.today().year)
    pack_actual = db.Column(db.String(30), default="Express")

    usuarios = db.relationship("Usuario", backref="empresa", lazy=True)
    balances = db.relationship(
        "Balance", backref="empresa", lazy=True, order_by="Balance.id.desc()"
    )


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    correo = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)


class Balance(db.Model):
    __tablename__ = "balances"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    archivo_nombre = db.Column(db.String(150), nullable=False)
    archivo_libro_mayor = db.Column(db.String(150))
    periodo = db.Column(db.String(20), nullable=False)
    estado = db.Column(db.String(30), default="Borrador")
    fecha_carga = db.Column(db.Date, default=date.today)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    cuentas = db.relationship(
        "CuentaContable", backref="balance", lazy=True, order_by="CuentaContable.codigo"
    )
    informes = db.relationship(
        "InformeEstadoResultados",
        backref="balance",
        lazy=True,
        order_by="InformeEstadoResultados.fecha_generacion.desc()",
    )


class CuentaContable(db.Model):
    __tablename__ = "cuentas_contables"

    id = db.Column(db.Integer, primary_key=True)
    balance_id = db.Column(db.Integer, db.ForeignKey("balances.id"), nullable=False)
    codigo = db.Column(db.String(20), nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    importe = db.Column(db.Float, nullable=False)
    categoria_niif = db.Column(db.String(50), nullable=False)
    revisado = db.Column(db.Boolean, default=False)
    observacion = db.Column(db.Text)

    movimientos = db.relationship(
        "MovimientoContable", backref="cuenta", lazy=True, order_by="MovimientoContable.fecha"
    )


class MovimientoContable(db.Model):
    __tablename__ = "movimientos_contables"

    id = db.Column(db.Integer, primary_key=True)
    cuenta_id = db.Column(db.Integer, db.ForeignKey("cuentas_contables.id"), nullable=False)
    fecha = db.Column(db.Date)
    num_transaccion = db.Column(db.String(50))
    detalle = db.Column(db.String(255))
    debe = db.Column(db.Float, default=0)
    haber = db.Column(db.Float, default=0)
    saldo_deudor = db.Column(db.Float, default=0)
    saldo_acreedor = db.Column(db.Float, default=0)


class InformeEstadoResultados(db.Model):
    __tablename__ = "informes_estado_resultados"

    id = db.Column(db.Integer, primary_key=True)
    balance_id = db.Column(db.Integer, db.ForeignKey("balances.id"), nullable=False)
    archivo_nombre = db.Column(db.String(200), nullable=False)
    periodo = db.Column(db.String(20), nullable=False)
    fecha_generacion = db.Column(db.DateTime, default=datetime.utcnow)


MEDIOS_PAGO = ["Tarjeta de crédito", "Tarjeta de débito", "Transferencia bancaria"]
PRECIO_INFORME_CLP = 12990


class Pago(db.Model):
    __tablename__ = "pagos"

    id = db.Column(db.Integer, primary_key=True)
    balance_id = db.Column(db.Integer, db.ForeignKey("balances.id"), nullable=False)
    monto = db.Column(db.Integer, nullable=False)
    medio_pago = db.Column(db.String(50), nullable=False)
    fecha_pago = db.Column(db.DateTime, default=datetime.utcnow)

    balance = db.relationship("Balance", backref=db.backref("pagos", lazy=True, order_by="Pago.fecha_pago.desc()"))


class CompraPackInforme(db.Model):
    __tablename__ = "compras_packs_informes"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False)
    nombre_pack = db.Column(db.String(30), nullable=False)
    informes_incluidos = db.Column(db.Integer, nullable=False)
    informes_usados = db.Column(db.Integer, nullable=False, default=0)
    precio = db.Column(db.Integer, nullable=False)
    medio_pago = db.Column(db.String(50))
    fecha_compra = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
