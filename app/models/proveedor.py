from app.extensions import db


class Proveedor(db.Model):
    """Proveedor de insumos. Soft-delete vía `activo` (nunca DELETE físico)."""

    __tablename__ = 'proveedor'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    rubro = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.Text)  # descripción libre del proveedor
    ubicacion = db.Column(db.String(200))  # dirección / zona (texto libre)
    telefono = db.Column(db.String(50))  # normalizado (misma regla que cliente)
    notas = db.Column(db.Text)  # días/condiciones de entrega
    activo = db.Column(db.Boolean, default=True, nullable=False)  # soft-delete

    insumos = db.relationship(
        'Insumo', back_populates='proveedor', order_by='Insumo.nombre'
    )

    def __repr__(self):
        return f'<Proveedor {self.nombre} ({self.rubro})>'


class Insumo(db.Model):
    """Insumo/mercadería comprada a un proveedor.

    `costo` es el último costo unitario, entero en centavos. Alimenta el costo
    de los artículos elaborados (que se recalcula en vivo, no se persiste).
    """

    __tablename__ = 'insumo'

    id = db.Column(db.Integer, primary_key=True)
    proveedor_id = db.Column(
        db.Integer, db.ForeignKey('proveedor.id'), nullable=False, index=True
    )
    nombre = db.Column(db.String(100), nullable=False)
    rubro = db.Column(db.String(50))
    costo = db.Column(db.Integer, nullable=False)  # (centavos) último costo unitario
    unidad = db.Column(db.String(20), nullable=False)  # kg, g, l, ml, ud
    activo = db.Column(db.Boolean, default=True, nullable=False)  # soft-delete

    proveedor = db.relationship('Proveedor', back_populates='insumos')
    lineas = db.relationship('ArticuloInsumo', back_populates='insumo')

    def __repr__(self):
        return f'<Insumo {self.nombre} ({self.costo} centavos/{self.unidad})>'
