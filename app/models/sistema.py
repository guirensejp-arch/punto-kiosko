from datetime import datetime

from app.extensions import db


class Configuracion(db.Model):
    """Flags globales del sistema. Una sola fila por instancia (single-tenant)."""

    __tablename__ = 'configuracion'

    id = db.Column(db.Integer, primary_key=True)
    fefo_activo = db.Column(db.Boolean, default=True, nullable=False)
    vista_ventas = db.Column(db.String(20), default='LISTA', nullable=False)
    modo_oscuro = db.Column(db.Boolean, default=False, nullable=False)
    font_size = db.Column(db.String(20), default='MEDIANO', nullable=False)
    impresora_termica = db.Column(db.String(100))
    # Lector de código de barras (HID / keyboard wedge).
    scan_terminador = db.Column(db.String(10), default='ENTER', nullable=False)
    scan_ms_entre_teclas = db.Column(db.Integer, default=120, nullable=False)
    scan_cantidad = db.Column(db.Integer, default=1, nullable=False)
    scan_prefijo_balanza = db.Column(db.String(5), default='2', nullable=False)

    @classmethod
    def get(cls):
        """Devuelve la fila única de configuración, creándola si no existe."""
        config = cls.query.first()
        if config is None:
            config = cls()
            db.session.add(config)
            db.session.commit()
        return config

    def __repr__(self):
        return '<Configuracion>'


class Auditoria(db.Model):
    """Registro transversal de acciones sensibles (quién, qué, cuándo)."""

    __tablename__ = 'auditoria'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    accion = db.Column(db.String(100), nullable=False)
    entidad = db.Column(db.String(50), nullable=False)
    entidad_id = db.Column(db.Integer)
    detalles = db.Column(db.JSON)
    fecha_hora = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    usuario = db.relationship('Usuario', backref='auditorias')

    def __repr__(self):
        return f'<Auditoria {self.accion} {self.entidad}#{self.entidad_id}>'
