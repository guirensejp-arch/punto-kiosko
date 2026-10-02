import secrets

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.decorators import admin_required
from app.extensions import db
from app.forms import UsuarioForm
from app.models.usuario import RolUsuario, Usuario
from app.utils.auditoria import registrar

usuarios_bp = Blueprint('usuarios', __name__, url_prefix='/usuarios')


@usuarios_bp.route('/')
@login_required
@admin_required
def lista():
    usuarios = Usuario.query.order_by(
        Usuario.activo.desc(), Usuario.apellido, Usuario.nombre
    ).all()
    return render_template('usuarios/lista.html', usuarios=usuarios)


@usuarios_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo():
    form = UsuarioForm()

    if form.validate_on_submit():
        if not form.password.data:
            flash('La contraseña es obligatoria al crear un usuario.', 'danger')
            return render_template('usuarios/form.html', form=form, usuario=None)

        email = form.email_personal.data.strip().lower()
        if Usuario.query.filter_by(email_personal=email).first():
            flash('Ya existe un usuario con ese email.', 'danger')
            return render_template('usuarios/form.html', form=form, usuario=None)

        usuario = Usuario(
            nombre=form.nombre.data.strip(),
            apellido=form.apellido.data.strip(),
            email_personal=email,
            rol=RolUsuario(form.rol.data),
            activo=form.activo.data,
        )
        usuario.set_password(form.password.data)
        db.session.add(usuario)
        db.session.commit()

        registrar('CREAR_USUARIO', 'usuario', usuario.id, {'rol': usuario.rol.value})
        flash(f'Usuario {usuario.nombre_completo} creado.', 'success')
        return redirect(url_for('usuarios.lista'))

    return render_template('usuarios/form.html', form=form, usuario=None)


@usuarios_bp.route('/<int:usuario_id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def editar(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    form = UsuarioForm(obj=usuario)

    if form.validate_on_submit():
        email = form.email_personal.data.strip().lower()
        duplicado = Usuario.query.filter(
            Usuario.email_personal == email, Usuario.id != usuario.id
        ).first()
        if duplicado:
            flash('Ya existe otro usuario con ese email.', 'danger')
            return render_template('usuarios/form.html', form=form, usuario=usuario)

        usuario.nombre = form.nombre.data.strip()
        usuario.apellido = form.apellido.data.strip()
        usuario.email_personal = email
        usuario.rol = RolUsuario(form.rol.data)

        if usuario.id == current_user.id:
            # Un admin no puede desactivarse ni quitarse el rol a sí mismo.
            usuario.activo = True
            if usuario.rol != RolUsuario.ADMIN:
                usuario.rol = RolUsuario.ADMIN
                flash('No podés quitarte el rol de administrador.', 'warning')
        else:
            usuario.activo = form.activo.data

        if form.password.data:
            usuario.set_password(form.password.data)

        db.session.commit()
        registrar('EDITAR_USUARIO', 'usuario', usuario.id)
        flash('Usuario actualizado.', 'success')
        return redirect(url_for('usuarios.lista'))

    return render_template('usuarios/form.html', form=form, usuario=usuario)


@usuarios_bp.route('/<int:usuario_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_password(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    temporal = secrets.token_hex(3)
    usuario.set_password(temporal)
    usuario.debe_cambiar_clave = True
    db.session.commit()

    registrar('RESET_CLAVE', 'usuario', usuario.id)
    flash(
        f'Clave temporal de {usuario.nombre_completo}: {temporal} '
        '(debe cambiarla en el próximo ingreso).',
        'warning',
    )
    return redirect(url_for('usuarios.lista'))


@usuarios_bp.route('/<int:usuario_id>/desactivar', methods=['POST'])
@login_required
@admin_required
def desactivar(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)

    if usuario.id == current_user.id:
        flash('No podés desactivar tu propio usuario.', 'danger')
        return redirect(url_for('usuarios.lista'))

    usuario.activo = False
    db.session.commit()

    registrar('DESACTIVAR_USUARIO', 'usuario', usuario.id)
    flash(f'Usuario {usuario.nombre_completo} desactivado.', 'info')
    return redirect(url_for('usuarios.lista'))


@usuarios_bp.route('/<int:usuario_id>/activar', methods=['POST'])
@login_required
@admin_required
def activar(usuario_id):
    usuario = db.get_or_404(Usuario, usuario_id)
    usuario.activo = True
    db.session.commit()

    registrar('ACTIVAR_USUARIO', 'usuario', usuario.id)
    flash(f'Usuario {usuario.nombre_completo} activado.', 'success')
    return redirect(url_for('usuarios.lista'))
