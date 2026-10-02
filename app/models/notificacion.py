import enum
from datetime import datetime

from app.extensions import db


class TipoNotificacion(enum.Enum):
    STOCK_BAJO = 'STOCK_BAJO'
    POR_VENCER = 'POR_VENCER'
    BAJO_MARGEN = 'BAJO_MARGEN'


class Notificacion(db.Model):
    """Alerta persistida (stock bajo / por vencer / bajo margen).

    Se generan por un cálculo idempotente y se descartan individual o
    globalmente; no se recalculan en vivo.
    """

    __tablename__ = 'notificacion'

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.Enum(TipoNotificacion), nullable=False)
    mensaje = db.Column(db.String(255), nullable=False)
    entidad = db.Column(db.String(50))  # lote, insumo, articulo
    entidad_id = db.Column(db.Integer)
    leida = db.Column(db.Boolean, default=False, nullable=False)
    descartada = db.Column(db.Boolean, default=False, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    fecha_hora = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    usuario = db.relationship('Usuario')

    def __repr__(self):
        return f'<Notificacion {self.tipo.value} {self.entidad}#{self.entidad_id}>'
