import os

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    send_file,
    url_for,
)
from flask_login import login_required

from app.decorators import admin_required
from app.extensions import db
from app.forms import ConfiguracionForm, MetodoPagoForm
from app.models.caja import MetodoPago
from app.models.sistema import Configuracion
from app.utils.auditoria import registrar

sistema_bp = Blueprint('sistema', __name__, url_prefix='/sistema')


@sistema_bp.route('/', methods=['GET', 'POST'])
@login_required
@admin_required
def index():
    config = Configuracion.get()
    form = ConfiguracionForm(obj=config)
    metodo_form = MetodoPagoForm()

    if form.validate_on_submit():
        form.populate_obj(config)
        db.session.commit()
        registrar('EDITAR_CONFIGURACION', 'configuracion', config.id)
        flash('Configuración guardada.', 'success')
        return redirect(url_for('sistema.index'))

    metodos = MetodoPago.query.order_by(MetodoPago.nombre).all()
    return render_template(
        'sistema.html', form=form, config=config,
        metodo_form=metodo_form, metodos=metodos,
    )


@sistema_bp.route('/metodos-pago', methods=['POST'])
@login_required
@admin_required
def nuevo_metodo_pago():
    form = MetodoPagoForm()
    if form.validate_on_submit():
        metodo = MetodoPago(
            nombre=form.nombre.data.strip(),
            es_efectivo=form.es_efectivo.data,
            activo=True,
        )
        db.session.add(metodo)
        db.session.commit()
        registrar('CREAR_METODO_PAGO', 'metodo_pago', metodo.id)
        flash('Método de pago agregado.', 'success')
    else:
        flash('Revisá el nombre del método de pago.', 'danger')
    return redirect(url_for('sistema.index'))


@sistema_bp.route('/metodos-pago/<int:metodo_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_metodo_pago(metodo_id):
    metodo = db.get_or_404(MetodoPago, metodo_id)
    metodo.activo = not metodo.activo
    db.session.commit()
    registrar('EDITAR_METODO_PAGO', 'metodo_pago', metodo.id)
    flash(
        f'Método {metodo.nombre} {"activado" if metodo.activo else "desactivado"}.',
        'info',
    )
    return redirect(url_for('sistema.index'))


@sistema_bp.route('/backup')
@login_required
@admin_required
def backup():
    """Descarga la base SQLite actual (backup manual)."""
    uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not uri.startswith('sqlite:///'):
        flash('El backup solo está disponible para bases SQLite.', 'warning')
        return redirect(url_for('sistema.index'))

    ruta = uri.replace('sqlite:///', '', 1)
    if not os.path.isabs(ruta):
        ruta = os.path.join(current_app.instance_path, ruta)
    if not os.path.exists(ruta):
        flash('No se encontró el archivo de base de datos.', 'danger')
        return redirect(url_for('sistema.index'))

    registrar('BACKUP_BASE', 'sistema')
    return send_file(ruta, as_attachment=True, download_name='comanda_backup.db')
