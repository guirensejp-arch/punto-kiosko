"""Ventas de kiosco: listado, punto de venta (cobro rápido), detalle y anulación.

El flujo es de mostrador: se agregan artículos (por escaneo, búsqueda o teclas),
se elige medio de pago y se cobra. El cliente es opcional.
"""

import json
from datetime import date, datetime, time, timedelta

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app.decorators import role_required
from app.extensions import db
from app.models.articulo import Articulo, CodigoBarras
from app.models.caja import MetodoPago
from app.models.cliente import Cliente
from app.models.promocion import Promocion
from app.models.sistema import Configuracion
from app.models.venta import (
    CLASES_ESTADO_VENTA,
    ETIQUETAS_ESTADO_VENTA,
    EstadoVenta,
    Venta,
)
from app.services import caja_service, promocion_service, venta_service
from app.services.phone_normalizer import normalize_phone
from app.utils.auditoria import registrar
from app.utils.numeros import parsear_decimal

ventas_bp = Blueprint('ventas', __name__, url_prefix='/ventas')

PERIODOS_HISTORIAL = {'HOY': 'Hoy', 'SEMANA': 'Semana', 'MES': 'Mes', 'TODO': 'Todo'}
_DIAS_PERIODO = {'HOY': 1, 'SEMANA': 7, 'MES': 30}


def _rango_periodo(periodo):
    """Inicio del rango para un período, o ``None`` (Todo)."""
    if periodo in _DIAS_PERIODO:
        return datetime.combine(
            date.today() - timedelta(days=_DIAS_PERIODO[periodo] - 1), time.min
        )
    return None


@ventas_bp.route('/')
@login_required
@role_required('ADMIN', 'CAJERO')
def lista():
    periodo = request.args.get('periodo') or 'HOY'
    estado = request.args.get('estado') or ''
    metodo_pago_id = request.args.get('metodo_pago', type=int)
    desde = request.args.get('desde') or ''
    hasta = request.args.get('hasta') or ''

    consulta = Venta.query
    if estado:
        try:
            consulta = consulta.filter(Venta.estado == EstadoVenta(estado))
        except ValueError:
            pass
    if metodo_pago_id:
        consulta = consulta.filter(Venta.metodo_pago_id == metodo_pago_id)

    # El rango puntual (desde/hasta) tiene prioridad sobre el período.
    if desde:
        consulta = consulta.filter(
            Venta.fecha_hora >= datetime.strptime(desde, '%Y-%m-%d')
        )
    if hasta:
        consulta = consulta.filter(
            Venta.fecha_hora
            <= datetime.strptime(hasta, '%Y-%m-%d').replace(hour=23, minute=59)
        )
    if not desde and not hasta:
        inicio = _rango_periodo(periodo)
        if inicio is not None:
            consulta = consulta.filter(Venta.fecha_hora >= inicio)

    ventas = consulta.order_by(Venta.fecha_hora.desc()).all()
    metodos = MetodoPago.query.order_by(MetodoPago.nombre).all()
    total_rango = sum(v.total for v in ventas if v.estado != EstadoVenta.ANULADA)

    return render_template(
        'ventas/lista.html',
        ventas=ventas,
        metodos=metodos,
        periodo=periodo,
        periodos=PERIODOS_HISTORIAL,
        estado=estado,
        metodo_pago_id=metodo_pago_id,
        desde=desde,
        hasta=hasta,
        total_rango=total_rango,
        etiquetas=ETIQUETAS_ESTADO_VENTA,
        clases=CLASES_ESTADO_VENTA,
    )


@ventas_bp.route('/nueva')
@login_required
@role_required('ADMIN', 'CAJERO')
def nueva():
    """Pantalla de punto de venta (cobro rápido)."""
    config = Configuracion.get()
    return render_template(
        'ventas/pos.html',
        config=config,
        turno=caja_service.turno_abierto(),
        metodos=MetodoPago.query.filter_by(activo=True).order_by(MetodoPago.nombre).all(),
        promociones=promocion_service.promociones_vigentes(),
        scan={
            'terminador': config.scan_terminador,
            'ms': config.scan_ms_entre_teclas or 120,
            'cantidad': config.scan_cantidad or 1,
            'prefijo_balanza': config.scan_prefijo_balanza or '2',
        },
    )


@ventas_bp.route('/buscar')
@login_required
@role_required('ADMIN', 'CAJERO')
def buscar():
    """Busca artículos por código de barras (exacto) o por texto (nombre/SKU).

    Devuelve JSON para el POS. Resuelve el escaneo antes que la búsqueda por texto.
    """
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({'articulos': []})

    articulos = []
    match = None
    codigo = (
        CodigoBarras.query.filter_by(codigo=q, activo=True)
        .first()
    )
    if codigo is not None and codigo.articulo.activo:
        articulos = [codigo.articulo]
        match = 'codigo'
    else:
        patron = f'%{q}%'
        articulos = (
            Articulo.query.filter(Articulo.activo.is_(True))
            .filter(
                db.or_(
                    Articulo.nombre.ilike(patron),
                    Articulo.sku.ilike(patron),
                )
            )
            .order_by(Articulo.nombre)
            .limit(20)
            .all()
        )

    return jsonify({'articulos': [_serializar(a) for a in articulos], 'match': match})


def _serializar(articulo):
    return {
        'id': articulo.id,
        'nombre': articulo.nombre,
        'categoria': articulo.categoria or '',
        'precio': articulo.precio_venta,
        'stock': float(articulo.stock) if articulo.stock is not None else None,
        'stock_propio': articulo.stock_propio,
        'es_pesable': articulo.es_pesable,
        'unidad': articulo.unidad,
        'codigos': [c.codigo for c in articulo.codigos if c.activo],
    }


@ventas_bp.route('/cobrar', methods=['POST'])
@login_required
@role_required('ADMIN', 'CAJERO')
def cobrar():
    """Cobra una venta. Acepta JSON o form; devuelve JSON con la venta creada."""
    datos = request.get_json(silent=True) or request.form
    try:
        crudo = datos.get('lineas')
        if isinstance(crudo, str):
            crudo = json.loads(crudo)
        lineas = _parsear_lineas(crudo or [])

        metodo_id = int(datos.get('metodo_pago_id') or 0)
        metodo_pago = db.session.get(MetodoPago, metodo_id) if metodo_id else None
        if metodo_pago is None:
            raise ValueError('Elegí un medio de pago.')

        descuento = int(datos.get('descuento') or 0)
        pago_recibido = int(datos.get('pago_recibido') or 0)
        cliente = _resolver_cliente(datos)
        notas = (datos.get('notas') or '').strip() or None

        promo = None
        descuento_promo = 0
        promo_id = int(datos.get('promocion_id') or 0)
        if promo_id:
            promo = db.session.get(Promocion, promo_id)
            if promo is None or not promo.vigente:
                raise ValueError('La promoción no está vigente.')
            descuento_promo = promocion_service.descuento_promocion(promo, lineas)
        else:
            promo, descuento_promo = promocion_service.mejor_automatica(lineas)

        turno = caja_service.turno_abierto()
        if turno is None:
            turno = caja_service.abrir_turno(0, current_user.id)

        venta = venta_service.crear_venta(
            lineas,
            current_user.id,
            cliente=cliente,
            metodo_pago=metodo_pago,
            notas=notas,
            descuento=descuento,
            promocion=promo,
            descuento_promocion=descuento_promo,
            pago_recibido=pago_recibido,
            turno=turno,
        )
        db.session.commit()
        registrar('CREAR_VENTA', 'venta', venta.id, {'total': venta.total})
        return jsonify({'ok': True, 'venta': _serializar_venta(venta)})
    except ValueError as error:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(error)}), 400
    except (TypeError, json.JSONDecodeError):
        db.session.rollback()
        return jsonify({'ok': False, 'error': 'Datos inválidos.'}), 400


def _parsear_lineas(crudas):
    lineas = []
    for item in crudas:
        articulo_id = item.get('articulo_id')
        cantidad = item.get('cantidad')
        if not articulo_id or cantidad in (None, ''):
            continue
        articulo = db.session.get(Articulo, int(articulo_id))
        if articulo is None or not articulo.activo:
            raise ValueError('Hay un artículo inválido o inactivo.')
        cant = parsear_decimal(str(cantidad))
        if cant is not None and not articulo.es_pesable:
            cant = cant.to_integral_value()
        if cant is None or cant <= 0:
            raise ValueError(f'Cantidad inválida para {articulo.nombre}.')
        lineas.append((articulo, cant))
    if not lineas:
        raise ValueError('Agregá al menos un artículo.')
    return lineas


def _resolver_cliente(datos):
    """Resuelve cliente opcional por id o por teléfono (venta anónima por defecto)."""
    cliente_id = datos.get('cliente_id')
    if cliente_id:
        cliente = db.session.get(Cliente, int(cliente_id))
        if cliente is not None:
            return cliente

    telefono = (datos.get('telefono') or '').strip()
    if not telefono:
        return None
    telefono = normalize_phone(telefono)
    if not telefono:
        raise ValueError('El teléfono no es válido.')
    cliente = Cliente.query.filter_by(telefono=telefono).first()
    if cliente is not None:
        return cliente
    nombre = (datos.get('cliente_nombre') or '').strip()
    if not nombre:
        raise ValueError('Para un cliente nuevo hace falta el nombre.')
    cliente = Cliente(nombre=nombre, telefono=telefono)
    db.session.add(cliente)
    db.session.flush()
    registrar('CREAR_CLIENTE', 'cliente', cliente.id, {'desde': 'pos'})
    return cliente


def _serializar_venta(venta):
    return {
        'id': venta.id,
        'numero': venta.numero,
        'total': venta.total,
        'vuelto': venta.vuelto,
        'metodo': venta.metodo_pago.nombre if venta.metodo_pago else '',
        'cantidad_items': venta.cantidad_items,
        'ticket_url': url_for('ventas.ticket', venta_id=venta.id),
    }


@ventas_bp.route('/<int:venta_id>')
@login_required
@role_required('ADMIN', 'CAJERO')
def detalle(venta_id):
    venta = db.get_or_404(Venta, venta_id)
    return render_template(
        'ventas/detalle.html',
        venta=venta,
        etiquetas=ETIQUETAS_ESTADO_VENTA,
        clases=CLASES_ESTADO_VENTA,
    )


@ventas_bp.route('/<int:venta_id>/ticket')
@login_required
@role_required('ADMIN', 'CAJERO')
def ticket(venta_id):
    """Comprobante de venta en formato ticket térmico 80mm (imprimible)."""
    venta = db.get_or_404(Venta, venta_id)
    return render_template('tickets/venta.html', venta=venta)


@ventas_bp.route('/<int:venta_id>/anular', methods=['POST'])
@login_required
@role_required('ADMIN', 'CAJERO')
def anular(venta_id):
    venta = db.get_or_404(Venta, venta_id)
    try:
        venta_service.anular_venta(venta, current_user.id)
        db.session.commit()
        registrar('ANULAR_VENTA', 'venta', venta.id)
        flash(f'Venta #{venta.numero} anulada.', 'info')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(url_for('ventas.detalle', venta_id=venta.id))
