from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.decorators import admin_required
from app.extensions import db
from app.forms import InsumoForm
from app.models.proveedor import Insumo, Proveedor
from app.utils.auditoria import registrar
from app.utils.moneda import centavos_a_editable, parsear_centavos

insumos_bp = Blueprint('insumos', __name__, url_prefix='/insumos')


def _cargar_choices(form):
    form.proveedor_id.choices = [
        (p.id, p.nombre) for p in Proveedor.query.order_by(Proveedor.nombre).all()
    ]


@insumos_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo():
    form = InsumoForm()
    _cargar_choices(form)

    if not form.is_submitted() and request.args.get('proveedor_id'):
        form.proveedor_id.data = request.args.get('proveedor_id', type=int)

    if form.validate_on_submit():
        try:
            costo = parsear_centavos(form.costo.data)
        except ValueError:
            flash('El costo no es un monto válido.', 'danger')
            return render_template('insumos/form.html', form=form, insumo=None)

        insumo = Insumo(
            proveedor_id=form.proveedor_id.data,
            nombre=form.nombre.data.strip(),
            rubro=(form.rubro.data or '').strip() or None,
            costo=costo,
            unidad=form.unidad.data,
            activo=form.activo.data,
        )
        db.session.add(insumo)
        db.session.commit()
        registrar('CREAR_INSUMO', 'insumo', insumo.id)
        flash(f'Insumo {insumo.nombre} creado.', 'success')
        return redirect(
            url_for('proveedores.detalle', proveedor_id=insumo.proveedor_id)
        )

    return render_template('insumos/form.html', form=form, insumo=None)


@insumos_bp.route('/<int:insumo_id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def editar(insumo_id):
    insumo = db.get_or_404(Insumo, insumo_id)
    form = InsumoForm(obj=insumo)
    _cargar_choices(form)

    if request.method == 'GET':
        form.costo.data = centavos_a_editable(insumo.costo)

    if form.validate_on_submit():
        try:
            insumo.costo = parsear_centavos(form.costo.data)
        except ValueError:
            flash('El costo no es un monto válido.', 'danger')
            return render_template('insumos/form.html', form=form, insumo=insumo)

        insumo.proveedor_id = form.proveedor_id.data
        insumo.nombre = form.nombre.data.strip()
        insumo.rubro = (form.rubro.data or '').strip() or None
        insumo.unidad = form.unidad.data
        insumo.activo = form.activo.data
        db.session.commit()
        registrar('EDITAR_INSUMO', 'insumo', insumo.id, {'costo': insumo.costo})
        flash('Insumo actualizado.', 'success')
        return redirect(
            url_for('proveedores.detalle', proveedor_id=insumo.proveedor_id)
        )

    return render_template('insumos/form.html', form=form, insumo=insumo)


@insumos_bp.route('/<int:insumo_id>/desactivar', methods=['POST'])
@login_required
@admin_required
def desactivar(insumo_id):
    insumo = db.get_or_404(Insumo, insumo_id)
    insumo.activo = False
    db.session.commit()
    registrar('DESACTIVAR_INSUMO', 'insumo', insumo.id)
    flash(f'Insumo {insumo.nombre} desactivado.', 'info')
    return redirect(url_for('proveedores.detalle', proveedor_id=insumo.proveedor_id))


@insumos_bp.route('/<int:insumo_id>/activar', methods=['POST'])
@login_required
@admin_required
def activar(insumo_id):
    insumo = db.get_or_404(Insumo, insumo_id)
    insumo.activo = True
    db.session.commit()
    registrar('ACTIVAR_INSUMO', 'insumo', insumo.id)
    flash(f'Insumo {insumo.nombre} activado.', 'success')
    return redirect(url_for('proveedores.detalle', proveedor_id=insumo.proveedor_id))
