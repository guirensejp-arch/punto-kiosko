from app.extensions import db


class Articulo(db.Model):
    """Artículo vendible en el kiosco.

    Dos modos de stock conviven:
    - ``stock_propio`` (reventa): el artículo tiene stock/fracción propia y se
      descuenta directo al venderse (ej. una gaseosa, un alfajor).
    - Receta (elaborado): el artículo arma su stock desde insumos
      (``articulo_insumo``), útil para café, panchos, etc.

    Un artículo puede tener además uno o más ``CodigoBarras`` (EAN/UPC interno),
    y un ``sku`` propio del negocio.
    """

    __tablename__ = 'articulo'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(255))
    categoria = db.Column(db.String(50))
    sku = db.Column(db.String(50), unique=True)
    precio_venta = db.Column(db.Integer, nullable=False)  # (centavos)
    precio_costo = db.Column(db.Integer, default=0, nullable=False)  # (centavos)
    margen_objetivo = db.Column(db.Integer)  # porcentaje informativo
    stock_propio = db.Column(db.Boolean, default=False, nullable=False)
    stock = db.Column(db.Numeric(12, 3), default=0, nullable=False)
    unidad = db.Column(db.String(20), default='ud', nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)  # soft-delete

    insumos = db.relationship(
        'ArticuloInsumo',
        back_populates='articulo',
        cascade='all, delete-orphan',
        order_by='ArticuloInsumo.id',
    )
    codigos = db.relationship(
        'CodigoBarras',
        back_populates='articulo',
        cascade='all, delete-orphan',
        order_by='CodigoBarras.id',
    )

    def __repr__(self):
        return f'<Articulo {self.nombre} ({self.precio_venta} centavos)>'


class CodigoBarras(db.Model):
    """Código de barras de un artículo (EAN-13, EAN-8, UPC-A, Code128, interno).

    Un artículo puede tener varios códigos (fabricante, interno, presentación).
    El código es único en todo el sistema para poder resolver por escaneo.
    """

    __tablename__ = 'codigo_barras'

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), nullable=False, unique=True, index=True)
    tipo = db.Column(db.String(20), default='EAN13', nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    articulo_id = db.Column(
        db.Integer, db.ForeignKey('articulo.id'), nullable=False, index=True
    )

    articulo = db.relationship('Articulo', back_populates='codigos')

    def __repr__(self):
        return f'<CodigoBarras {self.codigo} -> articulo {self.articulo_id}>'


class ArticuloInsumo(db.Model):
    """Línea de receta: unión artículo ↔ insumo con cantidad y unidad."""

    __tablename__ = 'articulo_insumo'
    __table_args__ = (
        db.UniqueConstraint('articulo_id', 'insumo_id', name='uq_articulo_insumo'),
    )

    id = db.Column(db.Integer, primary_key=True)
    articulo_id = db.Column(
        db.Integer, db.ForeignKey('articulo.id'), nullable=False, index=True
    )
    insumo_id = db.Column(
        db.Integer, db.ForeignKey('insumo.id'), nullable=False, index=True
    )
    cantidad = db.Column(db.Numeric(12, 3), nullable=False)
    unidad = db.Column(db.String(20), nullable=False)  # g, kg, ml, l

    articulo = db.relationship('Articulo', back_populates='insumos')
    insumo = db.relationship('Insumo', back_populates='lineas')

    def __repr__(self):
        return f'<ArticuloInsumo {self.articulo_id}-{self.insumo_id} {self.cantidad}{self.unidad}>'
