"""Analítica de gestión: KPIs, series y agrupaciones de solo lectura.

Sección independiente del Dashboard de Inicio (``dashboard_service``). No
persiste nada ni modifica modelos: todo se calcula con consultas agregadas
sobre los datos existentes. El dinero se mantiene como entero en centavos.

Métricas que son estimaciones (se marcan como tales en la UI):
- ``costo_estimado`` / ``margen_estimado``: food cost *actual* (``insumo.costo``
  se recalcula en vivo), no el costo histórico al momento de la venta.
- ``valor_stock``: valor a costo actual de los insumos, no costo por lote.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.caja import (
    Arqueo,
    MetodoPago,
    MovimientoCaja,
    TipoMovimientoCaja,
)
from app.models.cliente import Cliente
from app.models.inventario import Lote, MovimientoInventario, TipoMovimientoInventario
from app.models.venta import (
    EstadoVenta,
    Venta,
    VentaDetalle,
)
from app.models.proveedor import Insumo
from app.models.articulo import Articulo, ArticuloInsumo
from app.services.food_cost import costo_producto
from app.services.inventario_service import (
    ESTADO_POR_VENCER,
    ESTADO_VENCIDA,
    estado_lote,
    stock_disponible,
)

# Etiquetas de período (mismas que el Dashboard de Inicio).
PERIODOS = {
    'DIA': 'Día',
    'SEMANA': 'Semana',
    'MES': 'Mes',
    'HISTORICO': 'Histórico',
}
_DIAS = {'DIA': 1, 'SEMANA': 7, 'MES': 30}

# Criterios de orden de la tabla de articulos.
ORDENES = {'UNIDADES': 'Unidades', 'FACTURACION': 'Facturación'}

# Umbral de stock bajo (mismo criterio que las notificaciones).
UMBRAL_STOCK_BAJO = 1

ETIQUETAS_ORIGEN = {
    'MOSTRADOR': 'Mostrador',
    'WHATSAPP': 'WhatsApp',
    'PEDIDOSYA': 'PedidosYa',
    'RAPPI': 'Rappi',
    'OTRO': 'Otro',
}

ETIQUETAS_ENTREGA = {
    'RETIRO': 'Retiro',
    'DELIVERY': 'Delivery',
    'MOZO': 'Mozo',
}

ETIQUETAS_CATEGORIA_CAJA = {
    'PROVEEDOR': 'Compras a proveedores',
    'GASTO': 'Gastos',
    'RETIRO_DUENO': 'Retiros del dueño',
    'VUELTO': 'Vuelto',
    'OTRO': 'Otros egresos',
}


# --------------------------------------------------------------------------- #
# Períodos
# --------------------------------------------------------------------------- #

def _hoy():
    """Fecha de hoy en UTC: los ``fecha_hora`` se guardan con ``utcnow``."""
    return datetime.utcnow().date()


def _parsear_fecha(valor):
    try:
        return datetime.strptime(valor, '%Y-%m-%d')
    except (TypeError, ValueError):
        return None


def _etiqueta_rango(desde, hasta):
    partes = []
    if desde is not None:
        partes.append(desde.strftime('%d/%m/%Y'))
    if hasta is not None:
        partes.append(hasta.strftime('%d/%m/%Y'))
    return ' – '.join(partes) if partes else 'Histórico'


def _ventana(periodo, desde, hasta):
    """Devuelve (inicio, fin, etiqueta, comparable) para un período.

    ``fin`` es exclusivo (incluye todo el día ``hasta``). ``comparable`` indica
    si tiene sentido calcular la ventana anterior de igual longitud.
    """
    desde_dt = _parsear_fecha(desde)
    hasta_dt = _parsear_fecha(hasta)
    if desde_dt or hasta_dt:
        inicio = desde_dt or datetime.min
        fin = (hasta_dt + timedelta(days=1)) if hasta_dt else None
        return inicio, fin, _etiqueta_rango(desde_dt, hasta_dt), False

    if periodo in _DIAS:
        hoy = _hoy()
        inicio = datetime.combine(
            hoy - timedelta(days=_DIAS[periodo] - 1), time.min
        )
        fin = datetime.combine(hoy + timedelta(days=1), time.min)
        return inicio, fin, PERIODOS[periodo], True

    return None, None, PERIODOS['HISTORICO'], False


def rango(periodo='DIA', desde=None, hasta=None):
    """Ventana de análisis con su etiqueta y la ventana anterior (si aplica)."""
    inicio, fin, etiqueta, comparable = _ventana(periodo, desde, hasta)
    anterior = None
    if comparable:
        duracion = fin - inicio
        anterior = {'inicio': inicio - duracion, 'fin': inicio}
    return {
        'periodo': periodo,
        'inicio': inicio,
        'fin': fin,
        'etiqueta': etiqueta,
        'anterior': anterior,
        'comparable': comparable,
    }


def _filtrar(consulta, columna, ventana):
    if ventana['inicio'] is not None:
        consulta = consulta.filter(columna >= ventana['inicio'])
    if ventana['fin'] is not None:
        consulta = consulta.filter(columna < ventana['fin'])
    return consulta


def _clave(valor):
    return valor.value if hasattr(valor, 'value') else valor


# --------------------------------------------------------------------------- #
# KPIs de ventas y ventas
# --------------------------------------------------------------------------- #

def _pedidos_agregados(ventana):
    consulta = db.session.query(
        func.coalesce(func.sum(Venta.total), 0),
        func.count(Venta.id),
    ).filter(Venta.estado != EstadoVenta.ANULADA)
    consulta = _filtrar(consulta, Venta.fecha_hora, ventana)
    ventas, cantidad = consulta.one()

    unidades = db.session.query(
        func.coalesce(func.sum(VentaDetalle.cantidad), 0)
    ).join(Venta, Venta.id == VentaDetalle.venta_id).filter(
        Venta.estado != EstadoVenta.ANULADA
    )
    unidades = _filtrar(unidades, Venta.fecha_hora, ventana)
    return {
        'ventas': int(ventas or 0),
        'ventas': int(cantidad or 0),
        'unidades': int(unidades.scalar() or 0),
    }


def _costo_estimado(ventana):
    """Costo del período, estimado con el food cost actual de cada articulo."""
    filas = db.session.query(
        VentaDetalle.articulo_id,
        func.sum(VentaDetalle.cantidad),
    ).join(Venta, Venta.id == VentaDetalle.venta_id).filter(
        Venta.estado != EstadoVenta.ANULADA
    )
    filas = _filtrar(filas, Venta.fecha_hora, ventana)
    filas = filas.group_by(VentaDetalle.articulo_id).all()

    ids = [articulo_id for articulo_id, _ in filas]
    articulos = {}
    if ids:
        articulos = {
            articulo.id: articulo
            for articulo in Articulo.query.filter(Articulo.id.in_(ids))
            .options(
                selectinload(Articulo.insumos).selectinload(ArticuloInsumo.insumo)
            )
            .all()
        }

    total = 0
    for articulo_id, cantidad in filas:
        articulo = articulos.get(articulo_id)
        if articulo is None:
            continue
        total += int(cantidad) * costo_producto(articulo)
    return total


def resumen(periodo='DIA', desde=None, hasta=None):
    """KPIs principales del período, en centavos (excepto conteos)."""
    ventana = rango(periodo, desde, hasta)
    agregados = _pedidos_agregados(ventana)
    costo = _costo_estimado(ventana)
    flujo = _caja(ventana)
    return {
        'ventas': agregados['ventas'],
        'ventas': agregados['ventas'],
        'ticket_promedio': (
            round(agregados['ventas'] / agregados['ventas'])
            if agregados['ventas'] else 0
        ),
        'unidades': agregados['unidades'],
        'costo_estimado': costo,
        'margen_estimado': agregados['ventas'] - costo,
        'resultado_caja': flujo['resultado'],
    }


# --------------------------------------------------------------------------- #
# Series diarias
# --------------------------------------------------------------------------- #

def _serie(ventana):
    dia = func.date(Venta.fecha_hora)
    consulta = db.session.query(
        dia.label('dia'),
        func.coalesce(func.sum(Venta.total), 0),
        func.count(Venta.id),
    ).filter(Venta.estado != EstadoVenta.ANULADA)
    consulta = _filtrar(consulta, Venta.fecha_hora, ventana)
    filas = consulta.group_by(dia).order_by(dia).all()

    por_dia = {}
    for valor_dia, ventas, ventas in filas:
        clave = str(valor_dia)
        por_dia[clave] = {'ventas': int(ventas or 0), 'ventas': int(ventas or 0)}

    if ventana['inicio'] is not None:
        inicio = ventana['inicio'].date()
    elif por_dia:
        inicio = min(date.fromisoformat(clave) for clave in por_dia)
    else:
        return []

    if ventana['fin'] is not None:
        fin = ventana['fin'].date() - timedelta(days=1)
    else:
        fin = _hoy()
    fin = min(fin, _hoy())

    serie = []
    actual = inicio
    while actual <= fin:
        clave = actual.isoformat()
        valores = por_dia.get(clave, {'ventas': 0, 'ventas': 0})
        ventas = valores['ventas']
        serie.append({
            'fecha': clave,
            'etiqueta': actual.strftime('%d/%m'),
            'ventas': valores['ventas'],
            'ventas': ventas,
            'ticket': round(valores['ventas'] / ventas) if ventas else 0,
        })
        actual += timedelta(days=1)
    return serie


# --------------------------------------------------------------------------- #
# Agrupaciones de ventas
# --------------------------------------------------------------------------- #

def _agrupar(ventana, columna, etiquetas, sin_dato):
    consulta = db.session.query(
        columna,
        func.count(Venta.id),
        func.coalesce(func.sum(Venta.total), 0),
    ).filter(Venta.estado != EstadoVenta.ANULADA)
    consulta = _filtrar(consulta, Venta.fecha_hora, ventana)
    filas = consulta.group_by(columna).order_by(
        func.coalesce(func.sum(Venta.total), 0).desc()
    ).all()

    return [
        {
            'clave': _clave(valor),
            'etiqueta': etiquetas.get(_clave(valor), sin_dato),
            'ventas': int(cantidad or 0),
            'monto': int(monto or 0),
        }
        for valor, cantidad, monto in filas
    ]


def _ventas_por_metodo(ventana):
    etiqueta = func.coalesce(MetodoPago.nombre, 'Sin método')
    consulta = db.session.query(
        etiqueta,
        func.count(Venta.id),
        func.coalesce(func.sum(Venta.total), 0),
    ).select_from(Venta).outerjoin(
        MetodoPago, MetodoPago.id == Venta.metodo_pago_id
    ).filter(Venta.estado != EstadoVenta.ANULADA)
    consulta = _filtrar(consulta, Venta.fecha_hora, ventana)
    filas = consulta.group_by(etiqueta).order_by(
        func.coalesce(func.sum(Venta.total), 0).desc()
    ).all()
    return [
        {'etiqueta': nombre, 'ventas': int(cantidad or 0), 'monto': int(monto or 0)}
        for nombre, cantidad, monto in filas
    ]


def _ventas_por_origen(ventana):
    """En kiosco no hay origen: todas las ventas son de mostrador."""
    filas = db.session.query(
        func.count(Venta.id),
        func.coalesce(func.sum(Venta.total), 0),
    ).filter(Venta.estado != EstadoVenta.ANULADA)
    filas = _filtrar(filas, Venta.fecha_hora, ventana).one()
    return [{'etiqueta': 'Mostrador', 'ventas': int(filas[0] or 0), 'monto': int(filas[1] or 0)}]


def _ventas_por_entrega(ventana):
    """En kiosco no hay tipo de entrega: se retira en el local."""
    filas = db.session.query(
        func.count(Venta.id),
        func.coalesce(func.sum(Venta.total), 0),
    ).filter(Venta.estado != EstadoVenta.ANULADA)
    filas = _filtrar(filas, Venta.fecha_hora, ventana).one()
    return [{'etiqueta': 'Retiro', 'ventas': int(filas[0] or 0), 'monto': int(filas[1] or 0)}]


# --------------------------------------------------------------------------- #
# Productos
# --------------------------------------------------------------------------- #

def _productos(ventana, orden='UNIDADES'):
    consulta = db.session.query(
        Articulo,
        func.coalesce(func.sum(VentaDetalle.cantidad), 0),
        func.coalesce(func.sum(VentaDetalle.subtotal), 0),
    ).join(VentaDetalle, VentaDetalle.articulo_id == Articulo.id).join(
        Venta, Venta.id == VentaDetalle.venta_id
    ).filter(Venta.estado != EstadoVenta.ANULADA).options(
        selectinload(Articulo.insumos).selectinload(ArticuloInsumo.insumo)
    )
    consulta = _filtrar(consulta, Venta.fecha_hora, ventana)
    filas = consulta.group_by(Articulo.id).all()

    total_facturacion = sum(int(facturacion or 0) for _, _, facturacion in filas) or 1
    articulos = []
    for articulo, unidades, facturacion in filas:
        unidades = int(unidades or 0)
        facturacion = int(facturacion or 0)
        costo = unidades * costo_producto(articulo)
        articulos.append({
            'articulo': articulo,
            'unidades': unidades,
            'facturacion': facturacion,
            'precio_promedio': round(facturacion / unidades) if unidades else 0,
            'costo_estimado': costo,
            'margen_estimado': facturacion - costo,
            'participacion': round(facturacion * 100 / total_facturacion),
        })

    if orden == 'FACTURACION':
        articulos.sort(key=lambda fila: fila['facturacion'], reverse=True)
    else:
        articulos.sort(key=lambda fila: fila['unidades'], reverse=True)
    return articulos


# --------------------------------------------------------------------------- #
# Clientes
# --------------------------------------------------------------------------- #

def _clientes(ventana):
    filas = db.session.query(
        Venta.cliente_id,
        func.count(Venta.id),
        func.coalesce(func.sum(Venta.total), 0),
    ).filter(
        Venta.estado != EstadoVenta.ANULADA,
        Venta.cliente_id.isnot(None),
    )
    filas = _filtrar(filas, Venta.fecha_hora, ventana)
    filas = filas.group_by(Venta.cliente_id).all()

    compradores = len(filas)
    total_pedidos = sum(int(f[1] or 0) for f in filas)
    facturacion = sum(int(f[2] or 0) for f in filas)

    comparables = ventana['inicio'] is not None
    nuevos = compradores
    if comparables and filas:
        ids = [f[0] for f in filas]
        primeros = db.session.query(
            Venta.cliente_id,
            func.min(Venta.fecha_hora).label('primero'),
        ).filter(
            Venta.estado != EstadoVenta.ANULADA,
            Venta.cliente_id.isnot(None),
        ).group_by(Venta.cliente_id).subquery()

        consulta = db.session.query(func.count()).select_from(primeros).filter(
            primeros.c.cliente_id.in_(ids),
            primeros.c.primero >= ventana['inicio'],
        )
        if ventana['fin'] is not None:
            consulta = consulta.filter(primeros.c.primero < ventana['fin'])
        nuevos = int(consulta.scalar() or 0)

    ids = [f[0] for f in filas]
    clientes = {}
    if ids:
        clientes = {
            cliente.id: cliente
            for cliente in Cliente.query.filter(Cliente.id.in_(ids)).all()
        }

    top = sorted(filas, key=lambda f: int(f[2] or 0), reverse=True)[:10]
    tabla = [
        {
            'cliente': clientes.get(cliente_id),
            'ventas': int(ventas or 0),
            'facturacion': int(monto or 0),
            'ticket': round(int(monto or 0) / int(ventas)) if ventas else 0,
        }
        for cliente_id, ventas, monto in top
    ]

    return {
        'compradores': compradores,
        'nuevos': nuevos,
        'recurrentes': compradores - nuevos,
        'ventas': total_pedidos,
        'facturacion': facturacion,
        'ticket_promedio': round(facturacion / total_pedidos) if total_pedidos else 0,
        'comparable_nuevos': comparables,
        'top': tabla,
    }


# --------------------------------------------------------------------------- #
# Inventario
# --------------------------------------------------------------------------- #

def _inventario(ventana):
    insumos = Insumo.query.filter_by(activo=True).options(
        selectinload(Insumo.lotes)
    ).all()
    stock_bajo = [
        insumo for insumo in insumos
        if stock_disponible(insumo) <= UMBRAL_STOCK_BAJO
    ]

    lotes = Lote.query.filter(Lote.cantidad > 0).options(
        selectinload(Lote.insumo)
    ).all()
    por_vencer = [lote for lote in lotes if estado_lote(lote) == ESTADO_POR_VENCER]
    vencidos = [lote for lote in lotes if estado_lote(lote) == ESTADO_VENCIDA]

    valor_stock = 0
    for lote in lotes:
        if estado_lote(lote) == ESTADO_VENCIDA:
            continue
        cantidad = Decimal(str(lote.cantidad or 0))
        valor_stock += int(round(cantidad * Decimal(lote.insumo.costo)))

    movimientos = db.session.query(
        MovimientoInventario.insumo_id,
        MovimientoInventario.tipo,
        func.coalesce(func.sum(MovimientoInventario.cantidad), 0),
    )
    movimientos = _filtrar(movimientos, MovimientoInventario.fecha_hora, ventana)
    movimientos = movimientos.group_by(
        MovimientoInventario.insumo_id, MovimientoInventario.tipo
    ).all()

    por_insumo = {}
    mermas = ajustes = 0
    for insumo_id, tipo, cantidad in movimientos:
        cantidad = Decimal(str(cantidad or 0))
        fila = por_insumo.setdefault(
            insumo_id, {'consumo': Decimal('0'), 'merma': Decimal('0'), 'ajuste': Decimal('0')}
        )
        if tipo == TipoMovimientoInventario.SALIDA:
            fila['consumo'] += abs(cantidad)
        elif tipo == TipoMovimientoInventario.MERMA:
            fila['merma'] += abs(cantidad)
            mermas += 1
        elif tipo == TipoMovimientoInventario.AJUSTE:
            fila['ajuste'] += abs(cantidad)
            ajustes += 1

    ids = list(por_insumo)
    detalle_insumos = {}
    if ids:
        detalle_insumos = {
            insumo.id: insumo
            for insumo in Insumo.query.filter(Insumo.id.in_(ids)).all()
        }

    consumo = []
    for insumo_id, valores in por_insumo.items():
        insumo = detalle_insumos.get(insumo_id)
        if insumo is None:
            continue
        consumo.append({
            'insumo': insumo,
            'unidad': insumo.unidad,
            'consumo': valores['consumo'],
            'merma': valores['merma'],
            'ajuste': valores['ajuste'],
        })
    consumo.sort(key=lambda fila: fila['consumo'], reverse=True)

    return {
        'insumos': len(insumos),
        'stock_bajo': stock_bajo,
        'por_vencer': por_vencer,
        'vencidos': vencidos,
        'valor_stock': valor_stock,
        'mermas': mermas,
        'ajustes': ajustes,
        'consumo': consumo,
    }


# --------------------------------------------------------------------------- #
# Caja y flujo
# --------------------------------------------------------------------------- #

def _caja(ventana):
    filas = db.session.query(
        MovimientoCaja.tipo,
        MovimientoCaja.categoria,
        func.coalesce(func.sum(MovimientoCaja.monto), 0),
    )
    filas = _filtrar(filas, MovimientoCaja.fecha_hora, ventana)
    filas = filas.group_by(MovimientoCaja.tipo, MovimientoCaja.categoria).all()

    ventas = ingresos = egresos = 0
    por_categoria = {}
    for tipo, categoria, monto in filas:
        monto = int(monto or 0)
        if tipo == TipoMovimientoCaja.VENTA:
            ventas += monto
        elif tipo == TipoMovimientoCaja.INGRESO:
            ingresos += monto
        elif tipo == TipoMovimientoCaja.EGRESO:
            egresos += monto
            clave = _clave(categoria) or 'OTRO'
            por_categoria[clave] = por_categoria.get(clave, 0) + monto

    diferencias = db.session.query(
        func.coalesce(func.sum(Arqueo.diferencia), 0)
    )
    diferencias = _filtrar(diferencias, Arqueo.fecha_hora, ventana)
    diferencia = int(diferencias.scalar() or 0)

    egresos_detalle = [
        {
            'etiqueta': ETIQUETAS_CATEGORIA_CAJA.get(clave, clave.title()),
            'monto': monto,
        }
        for clave, monto in sorted(
            por_categoria.items(), key=lambda item: item[1], reverse=True
        )
    ]

    return {
        'ventas': ventas,
        'ingresos': ingresos,
        'egresos': egresos,
        'resultado': ventas + ingresos - egresos,
        'compras': por_categoria.get('PROVEEDOR', 0),
        'gastos': por_categoria.get('GASTO', 0),
        'retiros': por_categoria.get('RETIRO_DUENO', 0),
        'diferencia_arqueo': diferencia,
        'egresos_detalle': egresos_detalle,
    }


# --------------------------------------------------------------------------- #
# Comparación de períodos
# --------------------------------------------------------------------------- #

def _variacion(actual, anterior):
    if not anterior:
        return None
    return round((actual - anterior) * 100 / anterior)


def _comparacion(ventana):
    if ventana['anterior'] is None:
        return None

    actual = _pedidos_agregados(ventana)
    anterior = _pedidos_agregados(ventana['anterior'])

    def _fila(etiqueta, valor_actual, valor_anterior):
        return {
            'etiqueta': etiqueta,
            'actual': valor_actual,
            'anterior': valor_anterior,
            'variacion': _variacion(valor_actual, valor_anterior),
        }

    return {
        'ventas': _fila('Ventas', actual['ventas'], anterior['ventas']),
        'ventas': _fila('Pedidos', actual['ventas'], anterior['ventas']),
        'ticket': _fila(
            'Ticket promedio',
            round(actual['ventas'] / actual['ventas']) if actual['ventas'] else 0,
            round(anterior['ventas'] / anterior['ventas']) if anterior['ventas'] else 0,
        ),
        'unidades': _fila('Unidades', actual['unidades'], anterior['unidades']),
    }


# --------------------------------------------------------------------------- #
# Orquestador
# --------------------------------------------------------------------------- #

def datos(periodo='DIA', desde=None, hasta=None, orden='UNIDADES'):
    """Todo lo que consume la vista de Analítica, en una sola llamada."""
    if orden not in ORDENES:
        orden = 'UNIDADES'

    ventana = rango(periodo, desde, hasta)
    agregados = _pedidos_agregados(ventana)
    costo = _costo_estimado(ventana)
    flujo = _caja(ventana)
    serie = _serie(ventana)
    metodos = _ventas_por_metodo(ventana)
    origenes = _ventas_por_origen(ventana)
    entregas = _ventas_por_entrega(ventana)
    articulos = _productos(ventana, orden)

    resumen = {
        'ventas': agregados['ventas'],
        'ventas': agregados['ventas'],
        'ticket_promedio': (
            round(agregados['ventas'] / agregados['ventas'])
            if agregados['ventas'] else 0
        ),
        'unidades': agregados['unidades'],
        'costo_estimado': costo,
        'margen_estimado': agregados['ventas'] - costo,
        'resultado_caja': flujo['resultado'],
    }

    return {
        'ventana': ventana,
        'orden': orden,
        'resumen': resumen,
        'serie': serie,
        'metodos': metodos,
        'origenes': origenes,
        'entregas': entregas,
        'articulos': articulos,
        'clientes': _clientes(ventana),
        'inventario': _inventario(ventana),
        'caja': flujo,
        'comparacion': _comparacion(ventana),
    }


def graficos(datos):
    """Series listas para Chart.js (solo strings/números, JSON-serializable)."""
    serie = datos['serie']
    articulos = datos['articulos']
    por_unidades = sorted(articulos, key=lambda fila: fila['unidades'], reverse=True)[:10]
    por_facturacion = sorted(
        articulos, key=lambda fila: fila['facturacion'], reverse=True
    )[:10]

    return {
        'serie': {
            'labels': [fila['etiqueta'] for fila in serie],
            'ventas': [fila['ventas'] for fila in serie],
            'ventas': [fila['ventas'] for fila in serie],
            'ticket': [fila['ticket'] for fila in serie],
        },
        'metodos': {
            'labels': [fila['etiqueta'] for fila in datos['metodos']],
            'valores': [fila['monto'] for fila in datos['metodos']],
        },
        'origenes': {
            'labels': [fila['etiqueta'] for fila in datos['origenes']],
            'valores': [fila['monto'] for fila in datos['origenes']],
        },
        'entregas': {
            'labels': [fila['etiqueta'] for fila in datos['entregas']],
            'valores': [fila['monto'] for fila in datos['entregas']],
        },
        'top_unidades': {
            'labels': [fila['articulo'].nombre for fila in por_unidades],
            'valores': [fila['unidades'] for fila in por_unidades],
        },
        'top_facturacion': {
            'labels': [fila['articulo'].nombre for fila in por_facturacion],
            'valores': [fila['facturacion'] for fila in por_facturacion],
        },
    }


# Envoltorios públicos para tests y consultas puntuales.
def serie_diaria(periodo='DIA', desde=None, hasta=None):
    return _serie(rango(periodo, desde, hasta))


def ventas_por_metodo(periodo='DIA', desde=None, hasta=None):
    return _ventas_por_metodo(rango(periodo, desde, hasta))


def ventas_por_origen(periodo='DIA', desde=None, hasta=None):
    return _ventas_por_origen(rango(periodo, desde, hasta))


def ventas_por_entrega(periodo='DIA', desde=None, hasta=None):
    return _ventas_por_entrega(rango(periodo, desde, hasta))


def articulos(periodo='DIA', desde=None, hasta=None, orden='UNIDADES'):
    return _productos(rango(periodo, desde, hasta), orden)


def clientes(periodo='DIA', desde=None, hasta=None):
    return _clientes(rango(periodo, desde, hasta))


def inventario(periodo='DIA', desde=None, hasta=None):
    return _inventario(rango(periodo, desde, hasta))


def caja_flujo(periodo='DIA', desde=None, hasta=None):
    return _caja(rango(periodo, desde, hasta))


def comparacion(periodo='DIA', desde=None, hasta=None):
    return _comparacion(rango(periodo, desde, hasta))
