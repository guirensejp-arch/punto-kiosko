"""Lógica de ventas: alta transaccional (todo-o-nada) con stock y caja.

Al cobrar una venta se ejecuta, en una única transacción:
venta + venta_detalle + descuento de stock (propio del artículo o insumos por
receta, FEFO) + movimiento de caja (VENTA) + movimientos de inventario.
Si algo falla, rollback sin estado a medias.
"""

from decimal import Decimal

from app.extensions import db
from app.models.caja import TipoMovimientoCaja
from app.models.inventario import MovimientoInventario, TipoMovimientoInventario
from app.models.venta import EstadoVenta, Venta, VentaDetalle
from app.services import caja_service
from app.services.inventario_service import consumir_fefo, stock_disponible
from app.utils.unidades import convertir


def siguiente_numero():
    """Número interno correlativo (arranca en 1001)."""
    ultimo = db.session.query(db.func.max(Venta.numero)).scalar()
    return (ultimo or 1000) + 1


def requerimientos_insumos(lineas):
    """Insumos necesarios para las líneas con receta: ``{insumo: Decimal}``.

    Los artículos con ``stock_propio`` no consumen insumos (se descuentan por su
    propio stock). Convierte la cantidad de cada línea a la unidad del insumo.
    """
    requeridos = {}
    for articulo, cantidad in lineas:
        if articulo.stock_propio:
            continue
        for linea in articulo.insumos:
            cantidad_insumo = convertir(linea.cantidad, linea.unidad, linea.insumo.unidad)
            if cantidad_insumo is None:
                raise ValueError(
                    f'Unidad incompatible en la receta de {articulo.nombre}.'
                )
            requeridos[linea.insumo] = (
                requeridos.get(linea.insumo, Decimal('0'))
                + cantidad_insumo * cantidad
            )
    return requeridos


def validar_stock(lineas):
    """Verifica stock suficiente (propio o por insumos). Devuelve los requeridos."""
    for articulo, cantidad in lineas:
        if articulo.stock_propio and articulo.stock < cantidad:
            raise ValueError(
                f'Sin stock de {articulo.nombre}: disponible {articulo.stock} '
                f'{articulo.unidad}.'
            )
    requeridos = requerimientos_insumos(lineas)
    for insumo, requerido in requeridos.items():
        disponible = stock_disponible(insumo)
        if disponible < requerido:
            raise ValueError(
                f'Sin stock suficiente de {insumo.nombre}: '
                f'necesario {requerido} {insumo.unidad}, disponible {disponible}.'
            )
    return requeridos


def crear_venta(
    lineas,
    usuario_id,
    cliente=None,
    metodo_pago=None,
    notas=None,
    descuento=0,
    promocion=None,
    descuento_promocion=0,
    pago_recibido=0,
    turno=None,
):
    """Confirma una venta completa (la transacción y el commit son del caller)."""
    if not lineas:
        raise ValueError('La venta no tiene artículos.')
    lineas = [
        (articulo, Decimal(str(cantidad)))
        for articulo, cantidad in lineas
    ]
    for articulo, cantidad in lineas:
        if cantidad is None or cantidad <= 0:
            raise ValueError(f'Cantidad inválida para {articulo.nombre}.')
        if not articulo.es_pesable and cantidad != cantidad.to_integral_value():
            raise ValueError(f'{articulo.nombre} se vende por unidad, no por peso.')

    # Subtotal por línea redondeado a centavos (los pesables pueden dar decimal).
    subtotal = sum(
        int(round(articulo.precio_venta * cantidad)) for articulo, cantidad in lineas
    )
    if descuento < 0 or descuento > subtotal:
        raise ValueError('El descuento no puede superar el subtotal.')
    if descuento_promocion < 0 or descuento_promocion > subtotal - descuento:
        raise ValueError('El descuento de la promoción no puede superar el subtotal.')
    total = subtotal - descuento - descuento_promocion

    if metodo_pago is None:
        raise ValueError('El método de pago es obligatorio.')

    pago_recibido = pago_recibido or 0
    if metodo_pago.es_efectivo and pago_recibido and pago_recibido < total:
        raise ValueError('El efectivo recibido es menor que el total.')
    vuelto = (pago_recibido - total) if pago_recibido > total else 0

    requeridos = validar_stock(lineas)

    venta = Venta(
        numero=siguiente_numero(),
        cliente_id=cliente.id if cliente else None,
        usuario_id=usuario_id,
        metodo_pago_id=metodo_pago.id,
        turno_caja_id=turno.id if turno else None,
        estado=EstadoVenta.CONFIRMADA,
        notas=(notas or '').strip() or None,
        descuento=descuento,
        descuento_promocion=descuento_promocion,
        subtotal=subtotal,
        total=total,
        pago_recibido=pago_recibido,
        vuelto=vuelto,
        promocion_id=promocion.id if promocion else None,
    )
    db.session.add(venta)
    db.session.flush()

    for articulo, cantidad in lineas:
        db.session.add(
            VentaDetalle(
                venta_id=venta.id,
                articulo_id=articulo.id,
                cantidad=cantidad,
                precio_unitario=articulo.precio_venta,
                subtotal=int(round(articulo.precio_venta * cantidad)),
            )
        )
    db.session.flush()

    # Descuento de stock: propio del artículo (reventa) o por insumos (receta).
    for articulo, cantidad in lineas:
        if articulo.stock_propio:
            articulo.stock = articulo.stock - Decimal(str(cantidad))
            db.session.add(
                MovimientoInventario(
                    insumo_id=None,
                    articulo_id=articulo.id,
                    tipo=TipoMovimientoInventario.SALIDA,
                    cantidad=cantidad,
                    usuario_id=usuario_id,
                    motivo=f'Venta #{venta.numero}',
                    venta_id=venta.id,
                )
            )
    for insumo, requerido in requeridos.items():
        consumir_fefo(
            insumo, requerido, f'Venta #{venta.numero}', usuario_id,
            tipo=TipoMovimientoInventario.SALIDA, venta_id=venta.id,
        )

    # Asiento de venta en caja.
    if turno is not None:
        caja_service.registrar_movimiento(
            turno,
            TipoMovimientoCaja.VENTA,
            total,
            usuario_id,
            metodo_pago_id=metodo_pago.id,
            motivo=f'Venta #{venta.numero}',
        )

    return venta


def anular_venta(venta, usuario_id):
    """Anula una venta revirtiendo stock y caja (devolución)."""
    if venta.estado == EstadoVenta.ANULADA:
        raise ValueError('La venta ya está anulada.')

    # Revierte stock propio.
    for detalle in venta.detalles:
        articulo = detalle.articulo
        if articulo.stock_propio:
            articulo.stock = articulo.stock + Decimal(str(detalle.cantidad))
            db.session.add(
                MovimientoInventario(
                    insumo_id=None,
                    articulo_id=articulo.id,
                    tipo=TipoMovimientoInventario.AJUSTE,
                    cantidad=detalle.cantidad,
                    usuario_id=usuario_id,
                    motivo=f'Anulación venta #{venta.numero}',
                    venta_id=venta.id,
                )
            )

    # Revierte el asiento de caja con un egreso por el total de la venta.
    if venta.turno is not None:
        caja_service.registrar_movimiento(
            venta.turno,
            TipoMovimientoCaja.EGRESO,
            venta.total,
            usuario_id,
            metodo_pago_id=venta.metodo_pago_id,
            motivo=f'Anulación venta #{venta.numero}',
        )

    venta.estado = EstadoVenta.ANULADA
    db.session.flush()
    return venta
