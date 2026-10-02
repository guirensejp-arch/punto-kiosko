import enum
from datetime import date, datetime

from app.extensions import db


class TipoDescuento(enum.Enum):
    PORCENTAJE = 'PORCENTAJE'
    MONTO_FIJO = 'MONTO_FIJO'
    DOS_POR_UNO = 'DOS_POR_UNO'


class AplicacionPromocion(enum.Enum):
    AUTOMATICA = 'AUTOMATICA'
    MANUAL = 'MANUAL'


ETIQUETAS_ESTADO_PROMO = {
    'VIGENTE': 'Vigente',
    'FUTURA': 'Futura',
    'VENCIDA': 'Vencida',
    'INACTIVA': 'Inactiva',
}

CLASES_ESTADO_PROMO = {
    'VIGENTE': 'text-bg-success',
    'FUTURA': 'text-bg-warning',
    'VENCIDA': 'text-bg-danger',
    'INACTIVA': 'text-bg-secondary',
}


def _fecha(valor):
    return valor.date() if isinstance(valor, datetime) else valor


class Promocion(db.Model):
    """Promoción con vigencia, tipo de descuento y articulos alcanzados.

    Semántica de ``valor`` según ``tipo_descuento``:
    - ``PORCENTAJE``: porcentaje en centésimos (20% → 2000).
    - ``MONTO_FIJO``: centavos.
    - ``DOS_POR_UNO``: ``valor`` NULL (lógica "llevás 2 pagás 1").
    """

    __tablename__ = 'promocion'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    tipo_descuento = db.Column(db.Enum(TipoDescuento), nullable=False)
    valor = db.Column(db.Integer)  # (centésimos / centavos / NULL según el tipo)
    aplicacion = db.Column(
        db.Enum(AplicacionPromocion),
        nullable=False,
        default=AplicacionPromocion.MANUAL,
    )
    vigencia_desde = db.Column(db.DateTime, nullable=False)
    vigencia_hasta = db.Column(db.DateTime, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)  # soft-delete
    # "Eliminar" fake: oculta la promoción de la lista sin borrarla, para no
    # romper ventas históricos que la referencian (venta.promocion_id).
    eliminada = db.Column(db.Boolean, default=False, nullable=False)

    articulos = db.relationship(
        'PromocionProducto', back_populates='promocion', cascade='all, delete-orphan'
    )

    @property
    def estado(self):
        """Estado derivado: VIGENTE / FUTURA / VENCIDA / INACTIVA."""
        if not self.activo:
            return 'INACTIVA'
        hoy = date.today()
        desde = _fecha(self.vigencia_desde)
        hasta = _fecha(self.vigencia_hasta)
        if hoy < desde:
            return 'FUTURA'
        if hoy > hasta:
            return 'VENCIDA'
        return 'VIGENTE'

    @property
    def vigente(self):
        return self.estado == 'VIGENTE'

    def alcanza(self, articulo):
        """True si la promoción aplica al articulo indicado."""
        return any(linea.articulo_id == articulo.id for linea in self.articulos)

    def __repr__(self):
        return f'<Promocion {self.nombre} ({self.tipo_descuento.value})>'


class PromocionProducto(db.Model):
    """Unión promoción ↔ articulo alcanzado."""

    __tablename__ = 'promocion_producto'
    __table_args__ = (
        db.UniqueConstraint('promocion_id', 'articulo_id', name='uq_promocion_producto'),
    )

    id = db.Column(db.Integer, primary_key=True)
    promocion_id = db.Column(
        db.Integer, db.ForeignKey('promocion.id'), nullable=False, index=True
    )
    articulo_id = db.Column(
        db.Integer, db.ForeignKey('articulo.id'), nullable=False, index=True
    )

    promocion = db.relationship('Promocion', back_populates='articulos')
    articulo = db.relationship('Articulo')

    def __repr__(self):
        return f'<PromocionProducto {self.promocion_id}-{self.articulo_id}>'
