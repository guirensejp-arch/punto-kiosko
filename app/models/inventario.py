import enum
from datetime import datetime

from app.extensions import db


class TipoMovimientoInventario(enum.Enum):
    """Naturaleza de un movimiento de stock."""

    CARGA = 'CARGA'  # alta de lote (ingreso de mercadería)
    AJUSTE = 'AJUSTE'  # corrección positiva por conteo físico (sobrante)
    MERMA = 'MERMA'  # corrección negativa por conteo físico (faltante/desperdicio)
    SALIDA = 'SALIDA'  # consumo por venta de un venta


class Lote(db.Model):
    """Lote de un insumo: stock con su propia fecha de ingreso y vencimiento.

    El stock nunca se ve como un total: se desglosa por lote (base de FEFO y de
    las alertas de vencimiento). No usa soft-delete: el lote queda como
    historial aunque se agote o venza.
    """

    __tablename__ = 'lote'

    id = db.Column(db.Integer, primary_key=True)
    insumo_id = db.Column(
        db.Integer, db.ForeignKey('insumo.id'), nullable=False, index=True
    )
    numero = db.Column(db.String(50))  # nº de lote del proveedor (#41)
    cantidad = db.Column(db.Numeric(12, 3), nullable=False, default=0)  # en unidad del insumo
    unidad = db.Column(db.String(20), nullable=False)
    fecha_ingreso = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_vencimiento = db.Column(db.DateTime, nullable=False)

    insumo = db.relationship('Insumo', backref='lotes')
    movimientos = db.relationship(
        'MovimientoInventario',
        back_populates='lote',
        order_by='MovimientoInventario.fecha_hora.desc()',
    )

    def __repr__(self):
        return f'<Lote #{self.numero or self.id} {self.cantidad}{self.unidad}>'


class Conteo(db.Model):
    """Línea de conteo físico: stock del sistema vs contado, por insumo."""

    __tablename__ = 'conteo'

    id = db.Column(db.Integer, primary_key=True)
    insumo_id = db.Column(
        db.Integer, db.ForeignKey('insumo.id'), nullable=False, index=True
    )
    cantidad_sistema = db.Column(db.Numeric(12, 3), nullable=False)
    cantidad_contada = db.Column(db.Numeric(12, 3), nullable=False)
    diferencia = db.Column(db.Numeric(12, 3), nullable=False)  # sistema − contado
    motivo = db.Column(db.String(255))
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    fecha_hora = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    insumo = db.relationship('Insumo')
    usuario = db.relationship('Usuario')
    movimientos = db.relationship('MovimientoInventario', back_populates='conteo')

    def __repr__(self):
        return f'<Conteo {self.insumo_id} dif={self.diferencia}>'


class MovimientoInventario(db.Model):
    """Trazabilidad de todo cambio de stock que no proviene de una venta."""

    __tablename__ = 'movimiento_inventario'

    id = db.Column(db.Integer, primary_key=True)
    insumo_id = db.Column(
        db.Integer, db.ForeignKey('insumo.id'), nullable=True, index=True
    )
    articulo_id = db.Column(
        db.Integer, db.ForeignKey('articulo.id'), nullable=True, index=True
    )
    lote_id = db.Column(db.Integer, db.ForeignKey('lote.id'))
    conteo_id = db.Column(db.Integer, db.ForeignKey('conteo.id'))
    movimiento_caja_id = db.Column(db.Integer, db.ForeignKey('movimiento_caja.id'))
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'))
    tipo = db.Column(db.Enum(TipoMovimientoInventario), nullable=False)
    cantidad = db.Column(db.Numeric(12, 3), nullable=False)  # delta aplicado (+/−)
    motivo = db.Column(db.String(255))
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    fecha_hora = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    insumo = db.relationship('Insumo')
    articulo = db.relationship('Articulo')
    lote = db.relationship('Lote', back_populates='movimientos')
    conteo = db.relationship('Conteo', back_populates='movimientos')
    movimiento_caja = db.relationship('MovimientoCaja')
    venta = db.relationship('Venta')
    usuario = db.relationship('Usuario')

    def __repr__(self):
        return f'<MovimientoInventario {self.tipo.value} {self.cantidad}>'
