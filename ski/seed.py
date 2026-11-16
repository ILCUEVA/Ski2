"""Datos de ejemplo para poder navegar el diseño sin tener que cargar nada a mano.

Esto reproduce la empresa "Comercial Andina SpA" usada en las maquetas.
Cuando se construya la lógica real de carga/clasificación, este archivo
puede dejar de usarse o limitarse solo a un entorno de demo.
"""
from werkzeug.security import generate_password_hash

from models import Balance, CompraPackInforme, CuentaContable, Empresa, Usuario

USUARIO_DEMO_CORREO = "demo@balancea.com"
USUARIO_DEMO_PASSWORD = "Balancea2026"

CUENTAS_DEMO = [
    # codigo, nombre, importe, categoria_niif, revisado
    ("4100", "Ingresos por ventas", 480.0, "Operación", True),
    ("6100", "Costo de ventas", -288.0, "Operación", True),
    ("5100", "Gastos de administración", -162.0, "Operación", True),
    ("5200", "Gastos de ventas", -38.0, "Operación", True),
    ("4200", "Otros ingresos operativos", 4.0, "Operación", False),
    ("4500", "Rendimientos de inversiones", 8.0, "Inversión", True),
    ("2100", "Intereses de préstamos", -18.0, "Financiación", False),
    ("2400", "Impuestos a las ganancias", -25.6, "Impuestos a las ganancias", True),
]


def seed_demo_data(db):
    if Empresa.query.count() > 0:
        return

    empresa = Empresa(
        nombre="Comercial Andina SpA",
        tipo="PYME",
        pais="Chile",
        rubro="Comercial",
        moneda="CLP",
        anio_vigente=2026,
    )
    db.session.add(empresa)
    db.session.flush()
    db.session.add(
        CompraPackInforme(
            empresa_id=empresa.id,
            nombre_pack="Express",
            informes_incluidos=1,
            precio=12990,
        )
    )

    usuario = Usuario(
        nombre="Comercial Andina",
        correo=USUARIO_DEMO_CORREO,
        password_hash=generate_password_hash(USUARIO_DEMO_PASSWORD),
        empresa_id=empresa.id,
    )
    db.session.add(usuario)

    balance_2026 = Balance(
        empresa=empresa,
        archivo_nombre="Balance_2026.xlsx",
        periodo="2026",
        estado="Borrador",
    )
    balance_2025 = Balance(
        empresa=empresa,
        archivo_nombre="Balance_2025.xlsx",
        periodo="2025",
        estado="Archivado",
    )
    db.session.add_all([balance_2026, balance_2025])
    db.session.flush()

    for codigo, nombre, importe, categoria, revisado in CUENTAS_DEMO:
        db.session.add(
            CuentaContable(
                balance_id=balance_2026.id,
                codigo=codigo,
                nombre=nombre,
                importe=importe,
                categoria_niif=categoria,
                revisado=revisado,
            )
        )

    db.session.commit()
