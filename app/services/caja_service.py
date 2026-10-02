"""Lógica de caja: turnos, movimientos, arqueo y cierre.

Reglas clave del doc:
- El turno se abre con un fondo inicial variable y se cierra con un arqueo.
- Regla dura: si la diferencia de arqueo no es 0, no se cierra sin motivo y
  confirmación explícita.
- Ventas, ingresos y egresos son agregados sobre ``movimiento_caja``; nunca se
  persisten totales duplicados en el turno.
- Compra a proveedor: genera un egreso y da de alta los lotes (compra → lote).
"""

from datetime import datetime

from app.extensions import db
from app.models.caja import (
    Arqueo,
    CategoriaMovimientoCaja,
    EstadoTurno,
    MovimientoCaja,
    TipoMovimientoCaja,
    TurnoCaja,
)
from app.models.venta import Venta
from app.services.inventario_service import cargar_lote
from app.utils.unidades import convertir


def turno_abierto():
    """Devuelve el turno abierto actual, o ``None``."""
    return (
        TurnoCaja.query.filter_by(estado=EstadoTurno.ABIERTO)
        .order_by(TurnoCaja.fecha_apertura.desc())
        .first()
    )


def abrir_turno(fondo_inicial, usuario_id):
    """Abre un turno nuevo. Falla si ya hay uno abierto."""
    if turno_abierto() is not None:
        raise ValueError('Ya hay un turno de caja abierto.')
    if fondo_inicial < 0:
        raise ValueError('El fondo inicial no puede ser negativo.')

    turno = TurnoCaja(
        usuario_id=usuario_id,
        fondo_inicial=fondo_inicial,
        estado=EstadoTurno.ABIERTO,
    )
    db.session.add(turno)
    db.session.flush()
    return turno


def movimientos_ordenados(turno):
    return sorted(turno.movimientos, key=lambda m: m.fecha_hora, reverse=True)


def _suma(movs, tipo, solo_efectivo=False):
    total = 0
    for mov in movs:
        if mov.tipo != tipo:
            continue
        if solo_efectivo and not (mov.metodo_pago and mov.metodo_pago.es_efectivo):
            continue
        total += mov.monto
    return total


def ventas_por_metodo(turno):
    """Agrupa las ventas del turno por método de pago."""
    agrupado = {}
    for mov in turno.movimientos:
        if mov.tipo != TipoMovimientoCaja.VENTA:
            continue
        clave = mov.metodo_pago_id
        if clave not in agrupado:
            agrupado[clave] = {'metodo': mov.metodo_pago, 'cantidad': 0, 'monto': 0}
        agrupado[clave]['cantidad'] += 1
        agrupado[clave]['monto'] += mov.monto
    return list(agrupado.values())


def kpis_turno(turno):
    movs = turno.movimientos
    return {
        'ventas': _suma(movs, TipoMovimientoCaja.VENTA),
        'ventas': cantidad_pedidos(turno),
        'ingresos': _suma(movs, TipoMovimientoCaja.INGRESO),
        'egresos': _suma(movs, TipoMovimientoCaja.EGRESO),
    }


def cantidad_pedidos(turno):
    """Cantidad de ventas registrados en el turno."""
    return Venta.query.filter_by(turno_caja_id=turno.id).count()


def resumen_historial(turno):
    """Datos agregados de un turno para el historial de caja."""
    movs = turno.movimientos
    ventas = _suma(movs, TipoMovimientoCaja.VENTA)
    ingresos = _suma(movs, TipoMovimientoCaja.INGRESO)
    egresos = _suma(movs, TipoMovimientoCaja.EGRESO)
    return {
        'turno': turno,
        'fondo': turno.fondo_inicial,
        'ventas': ventas,
        'ingresos': ingresos,
        'egresos': egresos,
        'total_caja': ventas + ingresos - egresos,
        'ventas': cantidad_pedidos(turno),
        'diferencia': turno.arqueo.diferencia if turno.arqueo else 0,
    }


def efectivo_esperado(turno):
    """Efectivo que debería haber en la caja: fondo + ventas efectivo + ingresos − egresos."""
    return turno.fondo_inicial + efectivo_del_turno(turno)


def efectivo_del_turno(turno):
    movs = turno.movimientos
    return (
        _suma(movs, TipoMovimientoCaja.VENTA, solo_efectivo=True)
        + _suma(movs, TipoMovimientoCaja.INGRESO)
        - _suma(movs, TipoMovimientoCaja.EGRESO)
    )


def totales_cierre(turno):
    """Agregados para el cierre Z. IVA informativo sobre precios con IVA incluido."""
    movs = turno.movimientos
    ventas = _suma(movs, TipoMovimientoCaja.VENTA)
    ingresos = _suma(movs, TipoMovimientoCaja.INGRESO)
    egresos = _suma(movs, TipoMovimientoCaja.EGRESO)
    return {
        'ventas': ventas,
        'descuentos_cantidad': 0,
        'descuentos_monto': 0,
        'iva_informativo': round(ventas * 21 / 121),
        'ingresos': ingresos,
        'egresos': egresos,
        'total_caja': ventas + ingresos - egresos,
    }


def resumen_x(turno, efectivo_contado=None):
    """Arqueo parcial (cierre X): totales del turno SIN cerrarlo.

    No persiste nada: es un cálculo de solo lectura. La diferencia es
    informativa (no dispara la regla dura del cierre Z).
    """
    movs = turno.movimientos
    ventas = _suma(movs, TipoMovimientoCaja.VENTA)
    ingresos = _suma(movs, TipoMovimientoCaja.INGRESO)
    egresos = _suma(movs, TipoMovimientoCaja.EGRESO)
    esperado = efectivo_esperado(turno)
    diferencia = (efectivo_contado - esperado) if efectivo_contado is not None else None
    return {
        'ventas': ventas,
        'ventas_cantidad': cantidad_pedidos(turno),
        'ingresos': ingresos,
        'egresos': egresos,
        'total_caja': ventas + ingresos - egresos,
        'iva_informativo': round(ventas * 21 / 121),
        'fondo': turno.fondo_inicial,
        'efectivo_esperado': esperado,
        'efectivo_contado': efectivo_contado,
        'diferencia': diferencia,
    }


def registrar_movimiento(
    turno, tipo, monto, usuario_id, categoria=None,
    metodo_pago_id=None, proveedor_id=None, motivo=None,
):
    """Registra un movimiento en el turno (no hace commit)."""
    if monto <= 0:
        raise ValueError('El monto debe ser mayor a 0.')
    if tipo != TipoMovimientoCaja.VENTA and not (motivo or '').strip():
        raise ValueError('El motivo es obligatorio para ingresos y egresos.')

    movimiento = MovimientoCaja(
        turno_caja_id=turno.id,
        tipo=tipo,
        categoria=categoria,
        metodo_pago_id=metodo_pago_id,
        proveedor_id=proveedor_id,
        monto=monto,
        motivo=(motivo or '').strip() or None,
        usuario_id=usuario_id,
    )
    db.session.add(movimiento)
    db.session.flush()
    return movimiento


def cerrar_turno(
    turno, efectivo_contado, usuario_id,
    motivo_diferencia=None, diferencia_confirmada=False, desglose=None,
):
    """Registra el arqueo y cierra el turno (regla dura de diferencias)."""
    if turno.estado != EstadoTurno.ABIERTO:
        raise ValueError('El turno ya está cerrado.')

    esperado = efectivo_esperado(turno)
    diferencia = efectivo_contado - esperado

    if diferencia != 0 and (
        not (motivo_diferencia or '').strip() or not diferencia_confirmada
    ):
        raise ValueError(
            'Hay una diferencia: hay que indicar el motivo y confirmarla.'
        )

    arqueo = Arqueo(
        turno_caja_id=turno.id,
        efectivo_contado=efectivo_contado,
        desglose=desglose,
        diferencia=diferencia,
        motivo_diferencia=(motivo_diferencia or '').strip() or None,
        diferencia_confirmada=diferencia_confirmada,
        usuario_id=usuario_id,
    )
    db.session.add(arqueo)
    turno.estado = EstadoTurno.CERRADO
    turno.fecha_cierre = datetime.utcnow()
    db.session.flush()
    return arqueo


def registrar_compra(turno, proveedor, lineas, usuario_id, motivo=None):
    """Compra a proveedor: un egreso + un lote por línea (compra → lote automático).

    ``lineas`` es una lista de dicts con ``insumo``, ``cantidad``, ``unidad``,
    ``costo_unitario`` (centavos), ``numero`` y ``fecha_vencimiento``.
    Actualiza ``insumo.costo`` con el costo unitario de la compra.
    """
    total = 0
    normalizadas = []
    for linea in lineas:
        insumo = linea['insumo']
        cantidad_insumo = convertir(linea['cantidad'], linea['unidad'], insumo.unidad)
        if cantidad_insumo is None:
            raise ValueError(f'Unidad incompatible para {insumo.nombre}.')
        costo = int(linea['costo_unitario'])
        if costo <= 0:
            raise ValueError(f'El costo de {insumo.nombre} debe ser mayor a 0.')
        total += int(round(cantidad_insumo * costo))
        normalizadas.append(linea)

    if not normalizadas:
        raise ValueError('La compra no tiene insumos cargados.')
    if total <= 0:
        raise ValueError('El total de la compra debe ser mayor a 0.')

    movimiento = registrar_movimiento(
        turno,
        TipoMovimientoCaja.EGRESO,
        total,
        usuario_id,
        categoria=CategoriaMovimientoCaja.PROVEEDOR,
        proveedor_id=proveedor.id,
        motivo=motivo or f'Compra a {proveedor.nombre}',
    )

    for linea in normalizadas:
        insumo = linea['insumo']
        insumo.costo = int(linea['costo_unitario'])
        cargar_lote(
            insumo,
            linea.get('numero'),
            linea['cantidad'],
            linea['unidad'],
            None,
            linea['fecha_vencimiento'],
            usuario_id,
            motivo=f'Compra a {proveedor.nombre}',
            movimiento_caja_id=movimiento.id,
        )

    return movimiento
