"""Lógica de inventario: stock por lote, FEFO, estado de vencimiento y ajustes.

Reglas clave del doc:
- El stock se desglosa por lote; nunca se muestra un total único aislado.
- FEFO (First Expired, First Out): con ``configuracion.fefo_activo`` se consume
  primero el lote que vence antes. Con FEFO OFF se consume por antigüedad (FIFO).
- Lote vencido = bloqueo de venta.
- El conteo físico registra la diferencia como movimiento (merma/ajuste), nunca
  se sobreescribe en silencio.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app.extensions import db
from app.models.inventario import (
    Conteo,
    Lote,
    MovimientoInventario,
    TipoMovimientoInventario,
)
from app.models.sistema import Configuracion
from app.utils.unidades import convertir

# Un lote vence dentro de estos días (o antes) se considera "por vencer".
UMBRAL_POR_VENCER_DIAS = 3

CERO = Decimal('0.000')
TRES_DECIMALES = Decimal('0.001')

ESTADO_VENCIDA = 'VENCIDA'
ESTADO_POR_VENCER = 'POR_VENCER'
ESTADO_OK = 'OK'

ETIQUETAS_ESTADO = {
    ESTADO_VENCIDA: 'Vencida',
    ESTADO_POR_VENCER: 'Por vencer',
    ESTADO_OK: 'OK',
}

CLASES_ESTADO = {
    ESTADO_VENCIDA: 'text-bg-danger',
    ESTADO_POR_VENCER: 'text-bg-warning',
    ESTADO_OK: 'text-bg-success',
}


def _q(valor):
    """Cuantiza a 3 decimales (unidad de medida del inventario)."""
    return Decimal(str(valor or 0)).quantize(TRES_DECIMALES)


def stock_insumo(insumo):
    """Stock total del insumo, sumando sus lotes (en la unidad del insumo)."""
    return sum((_q(lote.cantidad) for lote in insumo.lotes), CERO)


def lotes_con_stock(insumo):
    return [lote for lote in insumo.lotes if _q(lote.cantidad) > CERO]


def _fecha(valor):
    return valor.date() if isinstance(valor, datetime) else valor


def esta_vencido(lote):
    return _fecha(lote.fecha_vencimiento) < date.today()


def orden_lotes(insumo, incluir_vencidos=False):
    """Lotes con stock en el orden de consumo (FEFO o FIFO según configuración).

    Por defecto excluye lotes vencidos: no se venden articulos con stock
    vencido. El conteo físico usa ``incluir_vencidos=True`` para poder
    descargar también esos lotes.
    """
    lotes = lotes_con_stock(insumo)
    if not incluir_vencidos:
        lotes = [lote for lote in lotes if not esta_vencido(lote)]
    if Configuracion.get().fefo_activo:
        return sorted(
            lotes, key=lambda lote: (lote.fecha_vencimiento, lote.fecha_ingreso)
        )
    return sorted(
        lotes, key=lambda lote: (lote.fecha_ingreso, lote.fecha_vencimiento)
    )


def stock_disponible(insumo):
    """Stock vendible: suma de lotes vigentes (no vencidos)."""
    return sum((_q(lote.cantidad) for lote in orden_lotes(insumo)), CERO)


def estado_lote(lote):
    """Estado derivado comparando el vencimiento con hoy."""
    vencimiento = lote.fecha_vencimiento
    if isinstance(vencimiento, datetime):
        vencimiento = vencimiento.date()
    hoy = date.today()
    if vencimiento < hoy:
        return ESTADO_VENCIDA
    if (vencimiento - hoy).days <= UMBRAL_POR_VENCER_DIAS:
        return ESTADO_POR_VENCER
    return ESTADO_OK


def registrar_movimiento(
    insumo, lote, tipo, cantidad, motivo, usuario_id,
    conteo_id=None, movimiento_caja_id=None, venta_id=None,
):
    """Agrega un movimiento de inventario a la sesión (no hace commit)."""
    movimiento = MovimientoInventario(
        insumo_id=insumo.id,
        lote_id=lote.id if lote else None,
        conteo_id=conteo_id,
        movimiento_caja_id=movimiento_caja_id,
        venta_id=venta_id,
        tipo=tipo,
        cantidad=_q(cantidad),
        motivo=motivo or None,
        usuario_id=usuario_id,
    )
    db.session.add(movimiento)
    return movimiento


def cargar_lote(
    insumo, numero, cantidad, unidad, fecha_ingreso, fecha_vencimiento,
    usuario_id, motivo='Carga de lote', movimiento_caja_id=None,
):
    """Da de alta un lote y registra el movimiento de carga."""
    cantidad_convertida = convertir(cantidad, unidad, insumo.unidad)
    if cantidad_convertida is None:
        raise ValueError('La unidad no es compatible con la del insumo.')

    if isinstance(fecha_ingreso, date) and not isinstance(fecha_ingreso, datetime):
        fecha_ingreso = datetime.combine(fecha_ingreso, time.min)
    if isinstance(fecha_vencimiento, date) and not isinstance(fecha_vencimiento, datetime):
        fecha_vencimiento = datetime.combine(fecha_vencimiento, time.min)

    lote = Lote(
        insumo_id=insumo.id,
        numero=(numero or '').strip() or None,
        cantidad=_q(cantidad_convertida),
        unidad=insumo.unidad,
        fecha_ingreso=fecha_ingreso or datetime.utcnow(),
        fecha_vencimiento=fecha_vencimiento,
    )
    db.session.add(lote)
    db.session.flush()

    registrar_movimiento(
        insumo, lote, TipoMovimientoInventario.CARGA, lote.cantidad,
        motivo, usuario_id, movimiento_caja_id=movimiento_caja_id,
    )
    return lote


def consumir_fefo(
    insumo, cantidad, motivo, usuario_id,
    tipo=TipoMovimientoInventario.MERMA, conteo_id=None,
    incluir_vencidos=False, venta_id=None,
):
    """Descuenta ``cantidad`` de los lotes en orden FEFO/FIFO.

    Registra un movimiento por cada lote afectado. Lanza ``ValueError`` si el
    stock disponible no alcanza (transacción todo-o-nada aguas arriba).
    """
    restante = _q(cantidad)
    movimientos = []
    if restante <= CERO:
        return movimientos

    for lote in orden_lotes(insumo, incluir_vencidos=incluir_vencidos):
        if restante <= CERO:
            break
        disponible = _q(lote.cantidad)
        tomar = min(disponible, restante)
        if tomar <= CERO:
            continue
        lote.cantidad = _q(disponible - tomar)
        movimientos.append(
            registrar_movimiento(
                insumo, lote, tipo, -tomar, motivo, usuario_id,
                conteo_id, venta_id=venta_id,
            )
        )
        restante = _q(restante - tomar)

    if restante > CERO:
        raise ValueError('No hay stock suficiente para cubrir el descuento.')

    return movimientos


def _agregar_stock(insumo, cantidad, motivo, usuario_id, conteo_id=None):
    """Suma stock sobrante de un conteo al lote de vencimiento más lejano."""
    lotes = list(insumo.lotes)
    if lotes:
        destino = max(lotes, key=lambda lote: lote.fecha_vencimiento)
    else:
        # No hay lotes previos: se crea uno de ajuste con vencimiento lejano.
        destino = Lote(
            insumo_id=insumo.id,
            numero='AJUSTE',
            cantidad=CERO,
            unidad=insumo.unidad,
            fecha_ingreso=datetime.utcnow(),
            fecha_vencimiento=datetime.utcnow() + timedelta(days=365),
        )
        db.session.add(destino)
        db.session.flush()

    destino.cantidad = _q(_q(destino.cantidad) + _q(cantidad))
    registrar_movimiento(
        insumo, destino, TipoMovimientoInventario.AJUSTE, cantidad,
        motivo, usuario_id, conteo_id,
    )
    return destino


def aplicar_conteo(insumo, cantidad_contada, motivo, usuario_id):
    """Reconcilia el stock del sistema con el conteo físico.

    Registra la línea de ``conteo`` y aplica el ajuste (merma si falta, alta si
    sobra). Devuelve el ``Conteo`` creado, o ``None`` si no hubo diferencia.
    """
    sistema = stock_insumo(insumo)
    contada = _q(cantidad_contada)
    diferencia = _q(sistema - contada)

    if diferencia == CERO:
        return None

    conteo = Conteo(
        insumo_id=insumo.id,
        cantidad_sistema=sistema,
        cantidad_contada=contada,
        diferencia=diferencia,
        motivo=motivo or None,
        usuario_id=usuario_id,
    )
    db.session.add(conteo)
    db.session.flush()

    if diferencia > CERO:
        consumir_fefo(
            insumo, diferencia, motivo, usuario_id,
            tipo=TipoMovimientoInventario.MERMA, conteo_id=conteo.id,
            incluir_vencidos=True,
        )
    else:
        _agregar_stock(insumo, -diferencia, motivo, usuario_id, conteo_id=conteo.id)

    return conteo
