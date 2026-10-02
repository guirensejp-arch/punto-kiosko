import enum
from datetime import datetime

from app.extensions import db


class EstadoVenta(enum.Enum):
    """Estados de una venta de kiosco: se cobra (CONFIRMADA) o se anula."""

    CONFIRMADA = 'CONFIRMADA'
    ANULADA = 'ANULADA'


ETIQUETAS_ESTADO_VENTA = {
    'CONFIRMADA': 'Confirmada',
    'ANULADA': 'Anulada',
}

CLASES_ESTADO_VENTA = {
    'CONFIRMADA': 'text-bg-success',
    'ANULADA': 'text-bg-danger',
}


class Venta(db.Model):
    """Venta de mostrador. No usa soft-delete: anular = estado ANULADA.

    Pensada para cobro rápido: el cliente es opcional (venta anónima) y no hay
    tipo de entrega ni cadete. El turno de caja asocia la venta al arqueo.
    """

    __tablename__ = 'venta'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.Integer, nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'))
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    metodo_pago_id = db.Column(db.Integer, db.ForeignKey('metodo_pago.id'))
    turno_caja_id = db.Column(db.Integer, db.ForeignKey('turno_caja.id'))
    estado = db.Column(db.Enum(EstadoVenta), nullable=False, default=EstadoVenta.CONFIRMADA)
    notas = db.Column(db.Text)
    descuento = db.Column(db.Integer, default=0, nullable=False)  # (centavos)
    descuento_promocion = db.Column(db.Integer, default=0, nullable=False)  # (centavos)
    subtotal = db.Column(db.Integer, default=0, nullable=False)  # (centavos)
    total = db.Column(db.Integer, default=0, nullable=False)  # (centavos)
    pago_recibido = db.Column(db.Integer, default=0, nullable=False)  # (centavos) efectivo entregado
    vuelto = db.Column(db.Integer, default=0, nullable=False)  # (centavos)
    promocion_id = db.Column(db.Integer, db.ForeignKey('promocion.id'))
    fecha_hora = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    cliente = db.relationship(
        'Cliente', backref=db.backref('ventas', order_by='Venta.fecha_hora.desc()')
    )
    usuario = db.relationship('Usuario', foreign_keys=[usuario_id])
    metodo_pago = db.relationship('MetodoPago')
    promocion = db.relationship('Promocion')
    turno = db.relationship('TurnoCaja')
    detalles = db.relationship(
        'VentaDetalle',
        back_populates='venta',
        cascade='all, delete-orphan',
        order_by='VentaDetalle.id',
    )

    @property
    def cantidad_items(self):
        return sum(detalle.cantidad for detalle in self.detalles)

    def __repr__(self):
        return f'<Venta #{self.numero} {self.estado.value} {self.total}>'


class VentaDetalle(db.Model):
    """Línea de venta: precio congelado al momento de la venta."""

    __tablename__ = 'venta_detalle'

    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(
        db.Integer, db.ForeignKey('venta.id'), nullable=False, index=True
    )
    articulo_id = db.Column(
        db.Integer, db.ForeignKey('articulo.id'), nullable=False, index=True
    )
    cantidad = db.Column(db.Numeric(12, 3), nullable=False)
    precio_unitario = db.Column(db.Integer, nullable=False)  # (centavos) congelado
    subtotal = db.Column(db.Integer, nullable=False)  # (centavos)

    venta = db.relationship('Venta', back_populates='detalles')
    articulo = db.relationship('Articulo')

    def __repr__(self):
        return f'<VentaDetalle {self.articulo_id} x{self.cantidad}>'
