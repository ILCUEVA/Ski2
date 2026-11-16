"""Seguimiento del avance del flujo (Subir información → Revisar clasificación →
Generar Estado de Rendimiento Financiero) y limpieza automática de balances
abandonados a medio camino.

Un balance se considera "completado" una vez que se generó al menos un
Estado de Rendimiento Financiero a partir de él (InformeEstadoResultados).
Mientras no esté completado, se cuenta como una sesión en progreso con un
plazo de MINUTOS_EXPIRACION desde su creación; si se cumple el plazo sin
completarse, se elimina junto con sus cuentas y movimientos para no dejar
borradores abandonados acumulándose en "Mis documentos".
"""
from datetime import datetime, timedelta

MINUTOS_EXPIRACION = 30
MINUTOS_ALERTA = 10  # a partir de aquí se muestra la alerta de tiempo restante


def calcular_progreso(balance):
    total = len(balance.cuentas)
    revisadas = sum(1 for c in balance.cuentas if c.revisado)
    completo = len(balance.informes) > 0

    if completo:
        paso = 3
        etiqueta = "Completado"
    elif total and revisadas == total:
        paso = 3
        etiqueta = "Paso 3 de 3 · Generar Estado de Rendimiento Financiero"
    elif total:
        paso = 2
        etiqueta = "Paso 2 de 3 · Revisar clasificación"
    else:
        paso = 1
        etiqueta = "Paso 1 de 3 · Subir Información Contable"

    creado = balance.creado_en or datetime.utcnow()
    vence = creado + timedelta(minutes=MINUTOS_EXPIRACION)
    segundos_restantes = (vence - datetime.utcnow()).total_seconds()
    minutos_restantes = max(0, int(segundos_restantes // 60))

    return {
        "paso": paso,
        "etiqueta": etiqueta,
        "completo": completo,
        "minutos_restantes": minutos_restantes,
        "por_vencer": (not completo) and minutos_restantes <= MINUTOS_ALERTA,
    }


def limpiar_balances_expirados(empresa, db):
    """Elimina (balance + cuentas + movimientos) cualquier borrador sin
    Estado de Rendimiento Financiero generado cuyo plazo ya haya vencido."""
    ahora = datetime.utcnow()
    eliminado_alguno = False

    for balance in list(empresa.balances):
        if balance.informes:
            continue
        creado = balance.creado_en or ahora
        if (ahora - creado) <= timedelta(minutes=MINUTOS_EXPIRACION):
            continue

        for cuenta in list(balance.cuentas):
            for movimiento in list(cuenta.movimientos):
                db.session.delete(movimiento)
            db.session.delete(cuenta)
        db.session.delete(balance)
        eliminado_alguno = True

    if eliminado_alguno:
        db.session.commit()
