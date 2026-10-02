from flask import Blueprint, flash, redirect, url_for
from flask_login import login_required

from app.extensions import db
from app.models.notificacion import Notificacion

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def index():
    """La pantalla de entrada de Punto Kiosko es el punto de venta."""
    return redirect(url_for('ventas.nueva'))


@main_bp.route('/notificaciones/<int:notificacion_id>/descartar', methods=['POST'])
@login_required
def descartar_notificacion(notificacion_id):
    notificacion = db.get_or_404(Notificacion, notificacion_id)
    notificacion.descartada = True
    db.session.commit()
    flash('Notificación descartada.', 'info')
    return redirect(url_for('main.index'))


@main_bp.route('/notificaciones/descartar', methods=['POST'])
@login_required
def descartar_todas():
    Notificacion.query.filter_by(descartada=False).update({'descartada': True})
    db.session.commit()
    flash('Notificaciones descartadas.', 'info')
    return redirect(url_for('main.index'))
