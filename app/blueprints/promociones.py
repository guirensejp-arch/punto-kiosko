from datetime import date, datetime, time

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required

from app.decorators import admin_required
from app.extensions import db
from app.forms import PromocionForm
from app.models.promocion import (
    CLASES_ESTADO_PROMO,
    ETIQUETAS_ESTADO_PROMO,
    AplicacionPromocion,
    Promocion,
    PromocionProducto,
    TipoDescuento,
)
from app.models.articulo import Articulo
from app.utils.auditoria import registrar
from app.utils.moneda import centavos_a_editable, parsear_centavos
from app.utils.numeros import parsear_decimal

promociones_bp = Blueprint('promociones', __name__, url_prefix='/promociones')


def _productos_activos():
    return Articulo.query.filter_by(activo=True).order_by(Articulo.nombre).all()


def _cargar_choices(form):
    form.articulos.choices = [
        (p.id, p.nombre) for p in _productos_activos()
    ]


def _parsear_valor(tipo, texto):
    if tipo == TipoDescuento.DOS_POR_UNO.value:
        return None
    if not texto or not texto.strip():
        raise ValueError('El valor es obligatorio para este tipo de descuento.')
    if tipo == TipoDescuento.PORCENTAJE.value:
        porcentaje = parsear_decimal(texto.replace('%', ''))
        if porcentaje is None or porcentaje <= 0 or porcentaje > 100:
            raise ValueError('El porcentaje debe estar entre 0 y 100.')
        return int(round(porcentaje * 100))  # centésimos
    monto = parsear_centavos(texto)
    if monto <= 0:
        raise ValueError('El monto debe ser mayor a 0.')
    return monto


def _guardar_productos(promocion, producto_ids):
    PromocionProducto.query.filter_by(promocion_id=promocion.id).delete()
    for articulo_id in producto_ids:
        db.session.add(
            PromocionProducto(promocion_id=promocion.id, articulo_id=articulo_id)
        )


@promociones_bp.route('/')
@login_required
def lista():
    promociones = Promocion.query.filter_by(eliminada=False).order_by(
        Promocion.activo.desc(), Promocion.nombre
    ).all()
    return render_template(
        'promociones/lista.html',
        promociones=promociones,
        etiquetas=ETIQUETAS_ESTADO_PROMO,
        clases=CLASES_ESTADO_PROMO,
    )


@promociones_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
@admin_required
def nueva():
    form = PromocionForm()
    _cargar_choices(form)

    if form.validate_on_submit():
        try:
            valor = _parsear_valor(form.tipo_descuento.data, form.valor.data)
            promo = Promocion(
                nombre=form.nombre.data.strip(),
                tipo_descuento=TipoDescuento(form.tipo_descuento.data),
                valor=valor,
                aplicacion=AplicacionPromocion(form.aplicacion.data),
                vigencia_desde=datetime.combine(form.vigencia_desde.data, time.min),
                vigencia_hasta=datetime.combine(form.vigencia_hasta.data, time.max),
                activo=form.activo.data,
            )
            db.session.add(promo)
            db.session.flush()
            _guardar_productos(promo, form.articulos.data)
            db.session.commit()
            registrar('CREAR_PROMOCION', 'promocion', promo.id)
            flash(f'Promoción {promo.nombre} creada.', 'success')
            return redirect(url_for('promociones.lista'))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')

    return render_template('promociones/form.html', form=form, promocion=None)


@promociones_bp.route('/<int:promocion_id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def editar(promocion_id):
    promo = db.get_or_404(Promocion, promocion_id)
    form = PromocionForm(obj=promo)
    _cargar_choices(form)

    if form.validate_on_submit():
        try:
            promo.nombre = form.nombre.data.strip()
            promo.tipo_descuento = TipoDescuento(form.tipo_descuento.data)
            promo.valor = _parsear_valor(form.tipo_descuento.data, form.valor.data)
            promo.aplicacion = AplicacionPromocion(form.aplicacion.data)
            promo.vigencia_desde = datetime.combine(form.vigencia_desde.data, time.min)
            promo.vigencia_hasta = datetime.combine(form.vigencia_hasta.data, time.max)
            promo.activo = form.activo.data
            _guardar_productos(promo, form.articulos.data)
            db.session.commit()
            registrar('EDITAR_PROMOCION', 'promocion', promo.id)
            flash('Promoción actualizada.', 'success')
            return redirect(url_for('promociones.lista'))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'danger')

    if not form.is_submitted():
        form.vigencia_desde.data = promo.vigencia_desde.date()
        form.vigencia_hasta.data = promo.vigencia_hasta.date()
        form.articulos.data = [linea.articulo_id for linea in promo.articulos]
        form.valor.data = (
            centavos_a_editable(promo.valor) if promo.valor is not None else ''
        )

    return render_template('promociones/form.html', form=form, promocion=promo)


@promociones_bp.route('/<int:promocion_id>/desactivar', methods=['POST'])
@login_required
@admin_required
def desactivar(promocion_id):
    promo = db.get_or_404(Promocion, promocion_id)
    promo.activo = False
    db.session.commit()
    registrar('DESACTIVAR_PROMOCION', 'promocion', promo.id)
    flash(f'Promoción {promo.nombre} desactivada.', 'info')
    return redirect(url_for('promociones.lista'))


@promociones_bp.route('/<int:promocion_id>/activar', methods=['POST'])
@login_required
@admin_required
def activar(promocion_id):
    promo = db.get_or_404(Promocion, promocion_id)
    promo.activo = True
    db.session.commit()
    registrar('ACTIVAR_PROMOCION', 'promocion', promo.id)
    flash(f'Promoción {promo.nombre} activada.', 'success')
    return redirect(url_for('promociones.lista'))


@promociones_bp.route('/<int:promocion_id>/eliminar', methods=['POST'])
@login_required
@admin_required
def eliminar(promocion_id):
    """Eliminar fake: oculta la promoción sin borrarla (preserva el histórico)."""
    promo = db.get_or_404(Promocion, promocion_id)
    promo.activo = False
    promo.eliminada = True
    db.session.commit()
    registrar('ELIMINAR_PROMOCION', 'promocion', promo.id)
    flash(f'Promoción {promo.nombre} eliminada.', 'info')
    return redirect(url_for('promociones.lista'))
