from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from openpyxl import Workbook
from sqlalchemy import func

from app.decorators import admin_required
from app.extensions import db
from app.forms import CompraInsumoForm, ProveedorForm
from app.models.inventario import Lote
from app.models.proveedor import Insumo, Proveedor
from app.services import caja_service
from app.services.inventario_service import (
    ESTADO_OK,
    ESTADO_POR_VENCER,
    ESTADO_VENCIDA,
    ETIQUETAS_ESTADO,
    estado_lote,
    stock_insumo,
)
from app.services.phone_normalizer import formatear_telefono, normalize_phone
from app.utils.auditoria import registrar
from app.utils.moneda import centavos_a_editable, parsear_centavos
from app.utils.numeros import parsear_decimal
from app.utils.excel import (
    FORMATO_MONEDA,
    ajustar_anchos,
    formatear_columna,
    marcar_encabezado,
    pesos,
    respuesta_xlsx,
)

proveedores_bp = Blueprint('proveedores', __name__, url_prefix='/proveedores')

_CLASES_BADGE = {
    ESTADO_OK: 'badge-estado-ok',
    ESTADO_POR_VENCER: 'badge-estado-por-vencer',
    ESTADO_VENCIDA: 'badge-estado-vencida',
}


def _info_insumos(proveedor):
    """Stock y estado de vencimiento por insumo (para el detalle)."""
    info = {}
    for insumo in proveedor.insumos:
        estados = [estado_lote(lote) for lote in insumo.lotes]
        if ESTADO_VENCIDA in estados:
            estado = ESTADO_VENCIDA
        elif ESTADO_POR_VENCER in estados:
            estado = ESTADO_POR_VENCER
        elif estados:
            estado = ESTADO_OK
        else:
            estado = None
        info[insumo.id] = {
            'stock': stock_insumo(insumo),
            'estado': estado,
            'etiqueta': ETIQUETAS_ESTADO.get(estado) if estado else None,
            'clase': _CLASES_BADGE.get(estado) if estado else None,
        }
    return info


@proveedores_bp.route('/')
@login_required
def lista():
    q = (request.args.get('q') or '').strip()
    rubro = (request.args.get('rubro') or '').strip()

    consulta = Proveedor.query
    if q:
        like = f'%{q}%'
        consulta = consulta.filter(
            db.or_(Proveedor.nombre.ilike(like), Proveedor.rubro.ilike(like))
        )
    if rubro:
        consulta = consulta.filter(Proveedor.rubro == rubro)

    proveedores = consulta.order_by(
        Proveedor.activo.desc(), Proveedor.nombre
    ).all()
    rubros = [
        r[0]
        for r in db.session.query(Proveedor.rubro)
        .distinct()
        .order_by(Proveedor.rubro)
        .all()
    ]
    ultimas_compras = dict(
        db.session.query(Proveedor.id, func.max(Lote.fecha_ingreso))
        .outerjoin(Insumo, Insumo.proveedor_id == Proveedor.id)
        .outerjoin(Lote, Lote.insumo_id == Insumo.id)
        .group_by(Proveedor.id)
        .all()
    )
    return render_template(
        'proveedores/lista.html',
        proveedores=proveedores,
        rubros=rubros,
        q=q,
        rubro=rubro,
        ultimas_compras=ultimas_compras,
    )


@proveedores_bp.route('/<int:proveedor_id>')
@login_required
def detalle(proveedor_id):
    proveedor = db.get_or_404(Proveedor, proveedor_id)
    return render_template(
        'proveedores/detalle.html',
        proveedor=proveedor,
        turno_abierto=caja_service.turno_abierto() is not None,
        info_insumos=_info_insumos(proveedor),
    )


@proveedores_bp.route(
    '/<int:proveedor_id>/insumos/<int:insumo_id>/compra', methods=['GET', 'POST']
)
@login_required
@admin_required
def compra_insumo(proveedor_id, insumo_id):
    """Compra de un insumo desde el detalle del proveedor.

    Genera egreso en caja + lote en inventario + ticket, reutilizando
    ``caja_service.registrar_compra``. Requiere turno de caja abierto.
    """
    proveedor = db.get_or_404(Proveedor, proveedor_id)
    insumo = db.get_or_404(Insumo, insumo_id)
    if insumo.proveedor_id != proveedor.id:
        flash('El insumo no pertenece a ese proveedor.', 'danger')
        return redirect(url_for('proveedores.detalle', proveedor_id=proveedor.id))

    turno = caja_service.turno_abierto()
    if turno is None:
        flash(
            'No hay un turno de caja abierto para registrar la compra.',
            'warning',
        )
        return redirect(url_for('caja.turno'))

    form = CompraInsumoForm()
    if request.method == 'GET':
        form.unidad.data = insumo.unidad
        form.costo.data = centavos_a_editable(insumo.costo)

    if form.validate_on_submit():
        try:
            cantidad = parsear_decimal(form.cantidad.data)
            if cantidad is None or cantidad <= 0:
                raise ValueError('La cantidad debe ser mayor a 0.')
            costo = parsear_centavos(form.costo.data)

            linea = {
                'insumo': insumo,
                'cantidad': cantidad,
                'unidad': form.unidad.data,
                'costo_unitario': costo,
                'numero': (form.numero.data or '').strip() or None,
                'fecha_vencimiento': form.fecha_vencimiento.data,
            }
            movimiento = caja_service.registrar_compra(
                turno,
                proveedor,
                [linea],
                current_user.id,
                motivo=(form.motivo.data or '').strip() or None,
            )
            db.session.commit()
            registrar(
                'COMPRA_PROVEEDOR',
                'proveedor',
                proveedor.id,
                {'insumo_id': insumo.id},
            )
            flash(f'Compra registrada: {insumo.nombre}.', 'success')
            return redirect(
                url_for('caja.compra_ticket', movimiento_id=movimiento.id, auto=1)
            )
        except (ValueError, KeyError) as error:
            db.session.rollback()
            flash(str(error), 'danger')

    return render_template(
        'proveedores/compra_insumo.html',
        form=form,
        proveedor=proveedor,
        insumo=insumo,
        stock=stock_insumo(insumo),
        turno=turno,
    )


@proveedores_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo():
    form = ProveedorForm()
    if form.validate_on_submit():
        proveedor = Proveedor(
            nombre=form.nombre.data.strip(),
            rubro=form.rubro.data.strip(),
            descripcion=(form.descripcion.data or '').strip() or None,
            ubicacion=(form.ubicacion.data or '').strip() or None,
            telefono=normalize_phone(form.telefono.data),
            notas=(form.notas.data or '').strip() or None,
            activo=form.activo.data,
        )
        db.session.add(proveedor)
        db.session.commit()
        registrar('CREAR_PROVEEDOR', 'proveedor', proveedor.id)
        flash(f'Proveedor {proveedor.nombre} creado.', 'success')
        return redirect(url_for('proveedores.detalle', proveedor_id=proveedor.id))

    return render_template('proveedores/form.html', form=form, proveedor=None)


@proveedores_bp.route('/<int:proveedor_id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def editar(proveedor_id):
    proveedor = db.get_or_404(Proveedor, proveedor_id)
    form = ProveedorForm(obj=proveedor)

    if form.validate_on_submit():
        proveedor.nombre = form.nombre.data.strip()
        proveedor.rubro = form.rubro.data.strip()
        proveedor.descripcion = (form.descripcion.data or '').strip() or None
        proveedor.ubicacion = (form.ubicacion.data or '').strip() or None
        proveedor.telefono = normalize_phone(form.telefono.data)
        proveedor.notas = (form.notas.data or '').strip() or None
        proveedor.activo = form.activo.data
        db.session.commit()
        registrar('EDITAR_PROVEEDOR', 'proveedor', proveedor.id)
        flash('Proveedor actualizado.', 'success')
        return redirect(url_for('proveedores.detalle', proveedor_id=proveedor.id))

    return render_template('proveedores/form.html', form=form, proveedor=proveedor)


@proveedores_bp.route('/<int:proveedor_id>/desactivar', methods=['POST'])
@login_required
@admin_required
def desactivar(proveedor_id):
    proveedor = db.get_or_404(Proveedor, proveedor_id)
    proveedor.activo = False
    db.session.commit()
    registrar('DESACTIVAR_PROVEEDOR', 'proveedor', proveedor.id)
    flash(f'Proveedor {proveedor.nombre} desactivado.', 'info')
    return redirect(url_for('proveedores.lista'))


@proveedores_bp.route('/<int:proveedor_id>/activar', methods=['POST'])
@login_required
@admin_required
def activar(proveedor_id):
    proveedor = db.get_or_404(Proveedor, proveedor_id)
    proveedor.activo = True
    db.session.commit()
    registrar('ACTIVAR_PROVEEDOR', 'proveedor', proveedor.id)
    flash(f'Proveedor {proveedor.nombre} activado.', 'success')
    return redirect(url_for('proveedores.lista'))


@proveedores_bp.route('/exportar.xlsx')
@login_required
def exportar_xlsx():
    proveedores = Proveedor.query.order_by(Proveedor.nombre).all()

    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Proveedores'
    hoja.append(
        ['Proveedor', 'Rubro', 'Descripción', 'Ubicación', 'Teléfono', 'Insumos', 'Estado', 'Notas']
    )
    for proveedor in proveedores:
        hoja.append([
            proveedor.nombre,
            proveedor.rubro,
            proveedor.descripcion or '',
            proveedor.ubicacion or '',
            formatear_telefono(proveedor.telefono),
            len(proveedor.insumos),
            'Activo' if proveedor.activo else 'Inactivo',
            proveedor.notas or '',
        ])
    marcar_encabezado(hoja)
    ajustar_anchos(hoja)
    hoja.freeze_panes = 'A2'

    hoja_insumos = libro.create_sheet('Insumos')
    hoja_insumos.append(
        ['Proveedor', 'Insumo', 'Rubro', 'Último costo', 'Unidad', 'Estado']
    )
    insumos = Insumo.query.order_by(Insumo.nombre).all()
    for insumo in insumos:
        hoja_insumos.append([
            insumo.proveedor.nombre if insumo.proveedor else '',
            insumo.nombre,
            insumo.rubro or '',
            pesos(insumo.costo),
            insumo.unidad,
            'Activo' if insumo.activo else 'Inactivo',
        ])
    marcar_encabezado(hoja_insumos)
    formatear_columna(hoja_insumos, 4, FORMATO_MONEDA)
    ajustar_anchos(hoja_insumos)
    hoja_insumos.freeze_panes = 'A2'

    return respuesta_xlsx(libro, 'proveedores.xlsx')
