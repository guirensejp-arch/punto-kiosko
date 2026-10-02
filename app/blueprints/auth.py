from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.forms import CambiarPasswordForm, LoginForm
from app.models.usuario import Usuario
from app.utils.auditoria import registrar

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        usuario = Usuario.query.filter_by(email_personal=email).first()

        if usuario and usuario.activo and usuario.check_password(form.password.data):
            login_user(usuario)
            registrar('LOGIN', 'usuario', usuario.id)
            flash(f'Bienvenido/a, {usuario.nombre}.', 'success')
            return redirect(url_for('main.index'))

        flash('Credenciales inválidas o usuario inactivo.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    registrar('LOGOUT', 'usuario', current_user.id)
    logout_user()
    flash('Sesión cerrada.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/cambiar-password', methods=['GET', 'POST'])
@login_required
def cambiar_password():
    form = CambiarPasswordForm()
    if form.validate_on_submit():
        current_user.set_password(form.password.data)
        current_user.debe_cambiar_clave = False
        db.session.commit()
        registrar('CAMBIAR_CLAVE', 'usuario', current_user.id)
        flash('Contraseña actualizada.', 'success')
        return redirect(url_for('main.index'))

    return render_template('auth/cambiar_password.html', form=form)
