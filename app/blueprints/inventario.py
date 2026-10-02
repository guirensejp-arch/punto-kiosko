from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from openpyxl import Workbook

from app.extensions import db
from app.forms import LoteForm
from app.models.inventario import Lote, Conteo, TipoMovimientoInventario
from app.models.proveedor import Insumo
from app.models.sistema import Configuracion
from app.services.inventario_service import (
    ESTADO_OK,
    ESTADO_POR_VENCER,
    ESTADO_VENCIDA,
    ETIQUETAS_ESTADO,
    UMBRAL_POR_VENCER_DIAS,
    aplicar_conteo,
    cargar_lote,
    estado_lote,
    stock_insumo,
)
from app.utils.auditoria import registrar
from app.utils.excel import (
    FORMATO_FECHA,
    ajustar_anchos,
    formatear_columna,
    marcar_encabezado,
    respuesta_xlsx,
)
from app.utils.numeros import parsear_decimal

inventario_bp = Blueprint('inventario', __name__, url_prefix='/inventario')


def _insumos_activos():
    return Insumo.query.filter_by(activo=True).order_by(Insumo.nombre).all()


@inventario_bp.route('/')
@login_required
def lista():
    q = (request.args.get('q') or '').strip()
    rubro = (request.args.get('rubro') or '').strip()
    vencimiento = (request.args.get('vencimiento') or '').strip()

    consulta = Lote.query.join(Insumo)
    if q:
        consulta = consulta.filter(Insumo.nombre.ilike(f'%{q}%'))
    if rubro:
        consulta = consulta.filter(Insumo.rubro == rubro)

    hoy = date.today()
    limite = hoy + timedelta(days=UMBRAL_POR_VENCER_DIAS)
    if vencimiento == ESTADO_VENCIDA:
        consulta = consulta.filter(Lote.fecha_vencimiento < hoy)
    elif vencimiento == ESTADO_POR_VENCER:
        consulta = consulta.filter(
            Lote.fecha_vencimiento >= hoy, Lote.fecha_vencimiento <= limite
        )
    elif vencimiento == ESTADO_OK:
        consulta = consulta.filter(Lote.fecha_vencimiento > limite)

    lotes = consulta.order_by(Insumo.nombre, Lote.fecha_vencimiento).all()
    rubros = [
        r[0]
        for r in db.session.query(Insumo.rubro)
        .filter(Insumo.rubro.isnot(None))
        .distinct()
        .order_by(Insumo.rubro)
        .all()
    ]

    return render_template(
        'inventario/lista.html',
        lotes=lotes,
        rubros=rubros,
        q=q,
        rubro=rubro,
        vencimiento=vencimiento,
        config=Configuracion.get(),
    )


@inventario_bp.route('/lote/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_lote():
    form = LoteForm()
    form.insumo_id.choices = [
        (i.id, f'{i.nombre} ({i.unidad})') for i in _insumos_activos()
    ]

    if form.validate_on_submit():
        insumo = db.session.get(Insumo, form.insumo_id.data)
        if insumo is None or not insumo.activo:
            flash('El insumo no existe o está inactivo.', 'danger')
        else:
            try:
                cantidad = parsear_decimal(form.cantidad.data)
                if cantidad is None or cantidad <= 0:
                    raise ValueError('La cantidad debe ser mayor a 0.')

                lote = cargar_lote(
                    insumo,
                    form.numero.data,
                    cantidad,
                    form.unidad.data,
                    form.fecha_ingreso.data,
                    form.fecha_vencimiento.data,
                    current_user.id,
                )
                db.session.commit()
                registrar('CARGAR_LOTE', 'lote', lote.id, {'insumo_id': insumo.id})
                flash(
                    f'Lote cargado: {insumo.nombre} ({lote.cantidad} {lote.unidad}).',
                    'success',
                )
                return redirect(
                    url_for('inventario.lote_ticket', lote_id=lote.id, auto=1)
                )
            except ValueError as error:
                db.session.rollback()
                flash(str(error), 'danger')

    return render_template('inventario/lote_form.html', form=form)


@inventario_bp.route('/conteo', methods=['GET', 'POST'])
@login_required
def conteo():
    insumos = _insumos_activos()

    if request.method == 'POST':
        motivo = (request.form.get('motivo') or '').strip()
        entradas = []

        for insumo in insumos:
            crudo = request.form.get(f'cantidad_{insumo.id}')
            if crudo is None or not crudo.strip():
                continue
            try:
                contada = parsear_decimal(crudo)
            except ValueError:
                flash(f'Cantidad inválida para {insumo.nombre}.', 'danger')
                return redirect(url_for('inventario.conteo'))
            entradas.append((insumo, contada))

        if not entradas:
            flash('No cargaste ninguna cantidad para contar.', 'warning')
            return redirect(url_for('inventario.conteo'))

        hay_diferencias = any(
            stock_insumo(insumo) - contada != 0 for insumo, contada in entradas
        )
        if hay_diferencias and not motivo:
            flash(
                'El motivo del ajuste es obligatorio cuando hay diferencias.',
                'danger',
            )
            return redirect(url_for('inventario.conteo'))

        try:
            conteos = [
                aplicar_conteo(insumo, contada, motivo, current_user.id)
                for insumo, contada in entradas
            ]
            db.session.commit()
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')
            return redirect(url_for('inventario.conteo'))

        for registro in conteos:
            if registro is not None:
                registrar(
                    'CONTEO_FISICO',
                    'insumo',
                    registro.insumo_id,
                    {'diferencia': str(registro.diferencia)},
                )

        ajustados = sum(1 for c in conteos if c is not None)
        if ajustados:
            flash(f'Conteo aplicado: {ajustados} insumo(s) con ajuste.', 'success')
        else:
            flash('Conteo aplicado sin diferencias.', 'info')
        primero = next((c for c in conteos if c is not None), None)
        if primero is not None:
            return redirect(
                url_for('inventario.conteo_ticket', conteo_id=primero.id, auto=1)
            )
        return redirect(url_for('inventario.lista'))

    return render_template('inventario/conteo.html', insumos=insumos)


@inventario_bp.route('/lote/<int:lote_id>/ticket')
@login_required
def lote_ticket(lote_id):
    """Comprobante de carga de un lote (ticket térmico 80mm)."""
    lote = db.get_or_404(Lote, lote_id)
    movimiento = next(
        (m for m in lote.movimientos if m.tipo == TipoMovimientoInventario.CARGA),
        None,
    )
    return render_template('tickets/lote.html', lote=lote, movimiento=movimiento)


@inventario_bp.route('/conteo/<int:conteo_id>/ticket')
@login_required
def conteo_ticket(conteo_id):
    """Comprobante de merma/ajuste derivado de un conteo físico."""
    conteo = db.get_or_404(Conteo, conteo_id)
    return render_template('tickets/conteo.html', conteo=conteo)


@inventario_bp.route('/exportar.xlsx')
@login_required
def exportar_xlsx():
    lotes = (
        Lote.query.join(Insumo)
        .order_by(Insumo.nombre, Lote.fecha_vencimiento)
        .all()
    )

    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Inventario'
    hoja.append(
        ['Insumo', 'Rubro', 'Lote', 'Ingreso', 'Vence', 'Estado', 'Stock', 'Unidad']
    )
    for lote in lotes:
        hoja.append([
            lote.insumo.nombre,
            lote.insumo.rubro or '',
            lote.numero or '',
            lote.fecha_ingreso,
            lote.fecha_vencimiento,
            ETIQUETAS_ESTADO[estado_lote(lote)],
            float(lote.cantidad),
            lote.unidad,
        ])

    marcar_encabezado(hoja)
    formatear_columna(hoja, 4, FORMATO_FECHA)
    formatear_columna(hoja, 5, FORMATO_FECHA)
    ajustar_anchos(hoja)
    hoja.freeze_panes = 'A2'

    return respuesta_xlsx(libro, 'inventario.xlsx')
