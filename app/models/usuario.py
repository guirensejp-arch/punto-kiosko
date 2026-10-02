import enum

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager


class RolUsuario(enum.Enum):
    """Roles del sistema. Lista cerrada y estable (enum, no tabla catálogo)."""

    ADMIN = 'ADMIN'
    CAJERO = 'CAJERO'


class Usuario(UserMixin, db.Model):
    """Usuario del sistema: Admin/Dueño o Cajero.

    Nombres de tabla/columnas en singular y snake_case (convención del proyecto).
    """

    __tablename__ = 'usuario'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=False)
    email_personal = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.Enum(RolUsuario), nullable=False, default=RolUsuario.CAJERO)
    debe_cambiar_clave = db.Column(db.Boolean, default=False, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)  # soft-delete

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def nombre_completo(self):
        return f'{self.nombre} {self.apellido}'

    @property
    def is_active(self):
        """Flask-Login: un usuario desactivado no puede iniciar sesión."""
        return self.activo

    def __repr__(self):
        return f'<Usuario {self.email_personal} ({self.rol.value})>'


@login_manager.user_loader
def load_user(user_id):
    """Carga el usuario de la sesión.

    Si el usuario fue desactivado, devuelve None: invalida la sesión ya abierta
    (no solo bloquea el próximo login).
    """
    usuario = db.session.get(Usuario, int(user_id))
    if usuario is None or not usuario.activo:
        return None
    return usuario
