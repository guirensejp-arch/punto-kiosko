import click
from flask.cli import with_appcontext

from app.extensions import db
from app.models.usuario import RolUsuario, Usuario


def init_app(app):
    """Registra los comandos de CLI de la aplicación."""
    app.cli.add_command(crear_admin)


@click.command('crear-admin')
@click.option('--email', prompt='Email', help='Email de login del administrador.')
@click.option('--nombre', prompt='Nombre')
@click.option('--apellido', prompt='Apellido')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
@with_appcontext
def crear_admin(email, nombre, apellido, password):
    """Crea un usuario ADMIN (dueño) inicial."""
    email = email.strip().lower()

    if Usuario.query.filter_by(email_personal=email).first():
        click.echo(f'Ya existe un usuario con el email {email}.')
        return

    usuario = Usuario(
        nombre=nombre.strip(),
        apellido=apellido.strip(),
        email_personal=email,
        rol=RolUsuario.ADMIN,
        activo=True,
    )
    usuario.set_password(password)
    db.session.add(usuario)
    db.session.commit()

    click.echo(f'Administrador creado: {email} (id {usuario.id}).')
