from datetime import datetime

from app.extensions import db


class Cliente(db.Model):
    """Cliente del negocio.

    El teléfono es el identificador natural (normalizado, UNIQUE): evita
    duplicados al poblarse automáticamente desde Pedidos.
    """

    __tablename__ = 'cliente'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100))
    telefono = db.Column(db.String(50), unique=True, nullable=False, index=True)
    direccion = db.Column(db.String(200))
    notas = db.Column(db.Text)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)  # soft-delete

    @property
    def nombre_completo(self):
        if self.apellido:
            return f'{self.apellido}, {self.nombre}'
        return self.nombre

    def __repr__(self):
        return f'<Cliente {self.nombre_completo} ({self.telefono})>'
