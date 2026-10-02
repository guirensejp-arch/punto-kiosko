"""Formularios de la app (Flask-WTF: validación + protección CSRF)."""

from datetime import date

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    IntegerField,
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

UNIDADES_CHOICES = [
    ('kg', 'kg'),
    ('g', 'g'),
    ('l', 'l'),
    ('ml', 'ml'),
    ('ud', 'ud'),
]

CATEGORIAS_CHOICES = [
    ('', 'Sin categoría'),
    ('Bebidas', 'Bebidas'),
    ('Golosinas', 'Golosinas'),
    ('Snacks', 'Snacks'),
    ('Cigarrillos', 'Cigarrillos'),
    ('Almacén', 'Almacén'),
    ('Kiosco', 'Kiosco'),
    ('Limpieza', 'Limpieza'),
    ('Perfumería', 'Perfumería'),
]


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired()])


class CambiarPasswordForm(FlaskForm):
    password = PasswordField(
        'Nueva contraseña',
        validators=[DataRequired(), Length(min=6, message='Mínimo 6 caracteres.')],
    )
    confirmar_password = PasswordField(
        'Repetir contraseña',
        validators=[DataRequired(), EqualTo('password', message='Las contraseñas no coinciden.')],
    )


class UsuarioForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    apellido = StringField('Apellido', validators=[DataRequired(), Length(max=100)])
    email_personal = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    rol = SelectField(
        'Rol',
        choices=[('ADMIN', 'Admin/Dueño'), ('CAJERO', 'Cajero')],
        validators=[DataRequired()],
    )
    # Obligatoria al crear; opcional al editar (vacío = no cambiar).
    password = PasswordField(
        'Contraseña',
        validators=[Optional(), Length(min=6, message='Mínimo 6 caracteres.')],
    )
    confirmar_password = PasswordField(
        'Repetir contraseña',
        validators=[Optional(), EqualTo('password', message='Las contraseñas no coinciden.')],
    )
    activo = BooleanField('Activo', default=True)


class ConfiguracionForm(FlaskForm):
    fefo_activo = BooleanField('FEFO activo (descontar primero lo que vence antes)')
    font_size = SelectField(
        'Tamaño de fuente',
        choices=[('CHICO', 'Chico'), ('MEDIANO', 'Mediano'), ('GRANDE', 'Grande')],
    )
    impresora_termica = StringField(
        'Impresora térmica',
        validators=[Optional(), Length(max=100)],
    )
    scan_terminador = SelectField(
        'Terminador del lector',
        choices=[('ENTER', 'Enter'), ('TAB', 'Tab'), ('NINGUNO', 'Ninguno (por tiempo)')],
    )
    scan_ms_entre_teclas = IntegerField(
        'Tiempo entre caracteres (ms)',
        validators=[Optional(), NumberRange(min=20, max=1000)],
    )
    scan_cantidad = IntegerField(
        'Cantidad por defecto al escanear',
        validators=[Optional(), NumberRange(min=1, max=999)],
    )
    scan_prefijo_balanza = StringField(
        'Prefijo de balanza (pesables)',
        validators=[Optional(), Length(max=5)],
    )


# ---------------------------------------------------------------------------
# Día 2 — Clientes, Proveedores, Insumos, Recetas/Productos
# ---------------------------------------------------------------------------


class ProveedorForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    rubro = StringField('Rubro', validators=[DataRequired(), Length(max=50)])
    descripcion = TextAreaField('Descripción', validators=[Optional(), Length(max=1000)])
    ubicacion = StringField('Ubicación', validators=[Optional(), Length(max=200)])
    telefono = StringField('Teléfono', validators=[Optional(), Length(max=50)])
    notas = TextAreaField('Notas', validators=[Optional(), Length(max=1000)])
    activo = BooleanField('Activo', default=True)


class InsumoForm(FlaskForm):
    proveedor_id = SelectField('Proveedor', coerce=int, validators=[DataRequired()])
    nombre = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    rubro = StringField('Rubro', validators=[Optional(), Length(max=50)])
    # Se carga como texto ("$ 7.000" o "7000") y se convierte a centavos.
    costo = StringField('Último costo', validators=[DataRequired(), Length(max=30)])
    unidad = SelectField('Unidad', choices=UNIDADES_CHOICES, validators=[DataRequired()])
    activo = BooleanField('Activo', default=True)


class CompraInsumoForm(FlaskForm):
    """Mini-form de compra: agrega unidades de un insumo desde el proveedor.

    Genera un egreso en caja + un lote en inventario (reusa
    ``caja_service.registrar_compra``). ``costo`` se carga como texto y se
    convierte a centavos en la ruta, igual que en Caja > Compras.
    """

    cantidad = StringField('Cantidad', validators=[DataRequired(), Length(max=30)])
    unidad = SelectField('Unidad', choices=UNIDADES_CHOICES, validators=[DataRequired()])
    costo = StringField('Costo unitario', validators=[DataRequired(), Length(max=30)])
    numero = StringField('Nº de lote', validators=[Optional(), Length(max=50)])
    fecha_vencimiento = DateField(
        'Fecha de vencimiento', validators=[DataRequired()]
    )
    motivo = StringField('Nota', validators=[Optional(), Length(max=255)])

    def validate_fecha_vencimiento(self, field):
        if field.data and field.data < date.today():
            raise ValidationError('La fecha de vencimiento no puede ser anterior a hoy.')


class ProductoForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    descripcion = TextAreaField('Descripción', validators=[Optional(), Length(max=255)])
    categoria = SelectField('Categoría', choices=CATEGORIAS_CHOICES)
    sku = StringField('SKU / código interno', validators=[Optional(), Length(max=50)])
    codigo_barras = StringField('Código de barras', validators=[Optional(), Length(max=50)])
    tipo = SelectField(
        'Cómo se maneja',
        choices=[
            ('DIRECTO', 'Vendo directo (llevo stock de este artículo)'),
            ('ELABORADO', 'Lo elaboro con insumos (receta)'),
        ],
    )
    # Se carga como texto ("$ 8.900" o "8900") y se convierte a centavos.
    precio_venta = StringField('Precio de venta', validators=[DataRequired(), Length(max=30)])
    precio_costo = StringField('Precio de costo', validators=[Optional(), Length(max=30)])
    stock = StringField('Stock', validators=[Optional(), Length(max=20)])
    unidad = SelectField('Unidad', choices=UNIDADES_CHOICES, default='ud')
    es_pesable = BooleanField('Se vende por peso (precio por kg/l)')
    margen_objetivo = IntegerField(
        'Margen objetivo (%)',
        validators=[Optional(), NumberRange(min=0, max=100)],
    )
    activo = BooleanField('Activo', default=True)


class ProductoInsumoForm(FlaskForm):
    insumo_id = SelectField('Insumo', coerce=int, validators=[DataRequired()])
    # Se acepta coma decimal ("0,150") y se parsea en la ruta.
    cantidad = StringField('Cantidad', validators=[DataRequired(), Length(max=30)])
    unidad = SelectField('Unidad', choices=UNIDADES_CHOICES, validators=[DataRequired()])


class LoteForm(FlaskForm):
    insumo_id = SelectField('Insumo', coerce=int, validators=[DataRequired()])
    numero = StringField('Nº de lote', validators=[Optional(), Length(max=50)])
    # Se acepta coma decimal ("3,2") y se parsea en la ruta.
    cantidad = StringField('Cantidad', validators=[DataRequired(), Length(max=30)])
    unidad = SelectField('Unidad', choices=UNIDADES_CHOICES, validators=[DataRequired()])
    fecha_ingreso = DateField('Fecha de ingreso', validators=[Optional()])
    fecha_vencimiento = DateField(
        'Fecha de vencimiento', validators=[DataRequired()]
    )

    def validate_fecha_vencimiento(self, field):
        if field.data and field.data < date.today():
            raise ValidationError('La fecha de vencimiento no puede ser anterior a hoy.')


# ---------------------------------------------------------------------------
# Día 4 — Caja
# ---------------------------------------------------------------------------


class AbrirTurnoForm(FlaskForm):
    # Se acepta coma decimal ("1.500,50") y se parsea en la ruta.
    fondo_inicial = StringField('Fondo inicial', validators=[DataRequired(), Length(max=30)])


class ArqueoForm(FlaskForm):
    efectivo_contado = StringField('Efectivo contado', validators=[DataRequired(), Length(max=30)])
    motivo_diferencia = TextAreaField('Motivo de la diferencia', validators=[Optional(), Length(max=1000)])
    diferencia_confirmada = BooleanField('Confirmo la diferencia y asumo la responsabilidad')


class MovimientoCajaForm(FlaskForm):
    tipo = SelectField(
        'Tipo',
        choices=[('INGRESO', 'Ingreso'), ('EGRESO', 'Egreso')],
        validators=[DataRequired()],
    )
    monto = StringField('Monto', validators=[DataRequired(), Length(max=30)])
    categoria = SelectField(
        'Categoría',
        choices=[
            ('', '—'),
            ('PROVEEDOR', 'Proveedor'),
            ('GASTO', 'Gasto'),
            ('RETIRO_DUENO', 'Retiro dueño'),
            ('VUELTO', 'Vuelto'),
            ('OTRO', 'Otro'),
        ],
        validators=[Optional()],
    )
    proveedor_id = SelectField('Vincular a proveedor', coerce=int, validators=[Optional()])
    motivo = StringField('Motivo / descripción', validators=[DataRequired(), Length(max=255)])


class MetodoPagoForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired(), Length(max=50)])
    es_efectivo = BooleanField('Es efectivo (impacta el arqueo)')


class CompraForm(FlaskForm):
    proveedor_id = SelectField('Proveedor', coerce=int, validators=[DataRequired()])
    motivo = StringField('Nota', validators=[Optional(), Length(max=255)])


# ---------------------------------------------------------------------------
# Ventas — cobro rápido (cliente opcional)
# ---------------------------------------------------------------------------


class VentaForm(FlaskForm):
    """Form de venta para el POS. El detalle se envía por JSON/JS."""

    telefono = StringField('Teléfono', validators=[Optional(), Length(max=50)])
    cliente_id = StringField('Cliente', validators=[Optional()])
    cliente_nombre = StringField('Nombre', validators=[Optional(), Length(max=100)])
    notas = TextAreaField('Notas', validators=[Optional(), Length(max=1000)])
    metodo_pago_id = SelectField('Medio de pago', coerce=int, validators=[Optional()])
    descuento = StringField('Descuento manual', validators=[Optional(), Length(max=30)])
    promocion_id = SelectField('Promoción', coerce=int, validators=[Optional()])


# ---------------------------------------------------------------------------
# Día 6 — Promociones
# ---------------------------------------------------------------------------


class PromocionForm(FlaskForm):
    nombre = StringField('Nombre', validators=[DataRequired(), Length(max=100)])
    tipo_descuento = SelectField(
        'Tipo de descuento',
        choices=[
            ('PORCENTAJE', 'Porcentaje (%)'),
            ('MONTO_FIJO', 'Monto fijo ($)'),
            ('DOS_POR_UNO', '2×1'),
        ],
        validators=[DataRequired()],
    )
    valor = StringField('Valor', validators=[Optional(), Length(max=30)])
    aplicacion = SelectField(
        'Aplicación',
        choices=[('AUTOMATICA', 'Automática'), ('MANUAL', 'Manual')],
        validators=[DataRequired()],
    )
    vigencia_desde = DateField('Vigente desde', validators=[DataRequired()])
    vigencia_hasta = DateField('Vigente hasta', validators=[DataRequired()])
    articulos = SelectMultipleField('Productos alcanzados', coerce=int, validators=[Optional()])
    activo = BooleanField('Activa', default=True)

    def validate_vigencia_hasta(self, field):
        if field.data and field.data < date.today():
            raise ValidationError('La vigencia no puede terminar en el pasado.')
        if field.data and self.vigencia_desde.data and field.data < self.vigencia_desde.data:
            raise ValidationError('La vigencia de fin no puede ser anterior al inicio.')
