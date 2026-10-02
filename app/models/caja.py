import enum

from app.extensions import db


class EstadoTurno(enum.Enum):
    ABIERTO = 'ABIERTO'
    CERRADO = 'CERRADO'


class TipoMovimientoCaja(enum.Enum):
    INGRESO = 'INGRESO'
    EGRESO = 'EGRESO'
    VENTA = 'VENTA'


class CategoriaMovimientoCaja(enum.Enum):
    PROVEEDOR = 'PROVEEDOR'
    GASTO = 'GASTO'
    RETIRO_DUENO = 'RETIRO_DUENO'
    VUELTO = 'VUELTO'
    OTRO = 'OTRO'


class MetodoPago(db.Model):
    """Método de pago configurable (Efectivo, QR, Débito, Crédito, MercadoPago).

    ``es_efectivo`` distingue el único método que impacta el arqueo de caja.
    """

    __tablename__ = 'metodo_pago'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    es_efectivo = db.Column(db.Boolean, default=False, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)  # soft-disable

    def __repr__(self):
        return f'<MetodoPago {self.nombre}>'


class TurnoCaja(db.Model):
    """Turno de caja: se abre con un fondo inicial y se cierra con un arqueo."""

    __tablename__ = 'turno_caja'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    fondo_inicial = db.Column(db.Integer, nullable=False)  # (centavos)
    estado = db.Column(db.Enum(EstadoTurno), nullable=False, default=EstadoTurno.ABIERTO)
    fecha_apertura = db.Column(db.DateTime, default=db.func.now(), nullable=False)
    fecha_cierre = db.Column(db.DateTime)

    usuario = db.relationship('Usuario')
    movimientos = db.relationship(
        'MovimientoCaja', back_populates='turno', order_by='MovimientoCaja.fecha_hora'
    )
    arqueo = db.relationship('Arqueo', back_populates='turno', uselist=False)

    def __repr__(self):
        return f'<TurnoCaja #{self.id} {self.estado.value}>'


class MovimientoCaja(db.Model):
    """Movimiento de caja: venta, ingreso extra o egreso.

    ``monto`` siempre positivo (centavos); el ``tipo`` define el signo. La
    ``categoria`` y el ``proveedor_id`` solo aplican a ingresos/egresos.
    """

    __tablename__ = 'movimiento_caja'

    id = db.Column(db.Integer, primary_key=True)
    turno_caja_id = db.Column(
        db.Integer, db.ForeignKey('turno_caja.id'), nullable=False, index=True
    )
    tipo = db.Column(db.Enum(TipoMovimientoCaja), nullable=False)
    categoria = db.Column(db.Enum(CategoriaMovimientoCaja))
    metodo_pago_id = db.Column(db.Integer, db.ForeignKey('metodo_pago.id'))
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'))
    monto = db.Column(db.Integer, nullable=False)  # (centavos) siempre > 0
    motivo = db.Column(db.String(255))
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    fecha_hora = db.Column(db.DateTime, default=db.func.now(), nullable=False)

    turno = db.relationship('TurnoCaja', back_populates='movimientos')
    metodo_pago = db.relationship('MetodoPago')
    proveedor = db.relationship('Proveedor')
    usuario = db.relationship('Usuario')

    def __repr__(self):
        return f'<MovimientoCaja {self.tipo.value} {self.monto}>'


class Arqueo(db.Model):
    """Arqueo de cierre: un único registro por turno.

    Regla dura: si ``diferencia != 0`` no se cierra sin motivo + confirmación.
    ``diferencia`` = efectivo contado − efectivo esperado (negativo = faltante).
    """

    __tablename__ = 'arqueo'

    id = db.Column(db.Integer, primary_key=True)
    turno_caja_id = db.Column(
        db.Integer, db.ForeignKey('turno_caja.id'), nullable=False, unique=True
    )
    efectivo_contado = db.Column(db.Integer, nullable=False, default=0)  # (centavos)
    desglose = db.Column(db.JSON)
    diferencia = db.Column(db.Integer, nullable=False, default=0)  # (centavos)
    motivo_diferencia = db.Column(db.Text)
    diferencia_confirmada = db.Column(db.Boolean, default=False, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    fecha_hora = db.Column(db.DateTime, default=db.func.now(), nullable=False)

    turno = db.relationship('TurnoCaja', back_populates='arqueo')
    usuario = db.relationship('Usuario')

    def __repr__(self):
        return f'<Arqueo turno={self.turno_caja_id} dif={self.diferencia}>'
