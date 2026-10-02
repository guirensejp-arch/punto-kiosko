"""Generación de notificaciones (stock bajo / por vencer / bajo margen).

La generación es idempotente: no vuelve a crear una notificación no descartada
para la misma entidad. Se ejecuta al abrir el Dashboard.
"""

from app.extensions import db
from app.models.inventario import Lote
from app.models.notificacion import Notificacion, TipoNotificacion
from app.models.proveedor import Insumo
from app.models.articulo import Articulo
from app.services.food_cost import costo_producto, margen_producto
from app.services.inventario_service import (
    ESTADO_POR_VENCER,
    estado_lote,
    stock_disponible,
)

UMBRAL_STOCK_BAJO = 1  # unidades base (kg/l/ud)
UMBRAL_MARGEN_BAJO = 30  # %


def _crear(tipo, mensaje, entidad, entidad_id, usuario_id=None):
    existente = Notificacion.query.filter_by(
        tipo=tipo, entidad=entidad, entidad_id=entidad_id, descartada=False
    ).first()
    if existente is not None:
        return False
    db.session.add(
        Notificacion(
            tipo=tipo,
            mensaje=mensaje,
            entidad=entidad,
            entidad_id=entidad_id,
            usuario_id=usuario_id,
        )
    )
    return True


def generar(usuario_id=None):
    """Recorre insumos, lotes y articulos y crea las alertas faltantes."""
    creadas = 0

    for insumo in Insumo.query.filter_by(activo=True).all():
        disponible = stock_disponible(insumo)
        if disponible <= UMBRAL_STOCK_BAJO:
            if _crear(
                TipoNotificacion.STOCK_BAJO,
                f'Stock bajo: {insumo.nombre} (quedan {disponible} {insumo.unidad})',
                'insumo',
                insumo.id,
                usuario_id,
            ):
                creadas += 1

    for lote in Lote.query.filter(Lote.cantidad > 0).all():
        if estado_lote(lote) == ESTADO_POR_VENCER:
            if _crear(
                TipoNotificacion.POR_VENCER,
                f'Por vencer: {lote.insumo.nombre} '
                f'(vence {lote.fecha_vencimiento.strftime("%d/%m")}, '
                f'lote #{lote.numero or lote.id})',
                'lote',
                lote.id,
                usuario_id,
            ):
                creadas += 1

    for articulo in Articulo.query.filter_by(activo=True).all():
        margen = margen_producto(articulo)
        if (
            margen is not None
            and costo_producto(articulo) > 0
            and margen < UMBRAL_MARGEN_BAJO
        ):
            if _crear(
                TipoNotificacion.BAJO_MARGEN,
                f'Bajo margen: {articulo.nombre} ({margen}%)',
                'articulo',
                articulo.id,
                usuario_id,
            ):
                creadas += 1

    db.session.commit()
    return creadas


def activas():
    return (
        Notificacion.query.filter_by(descartada=False)
        .order_by(Notificacion.fecha_hora.desc())
        .all()
    )
