"""Registro central de modelos.

Importar este paquete deja todos los modelos disponibles en SQLAlchemy,
necesario para que Flask-Migrate detecte el esquema.
"""

from app.models.articulo import Articulo, ArticuloInsumo, CodigoBarras
from app.models.caja import (
    Arqueo,
    CategoriaMovimientoCaja,
    EstadoTurno,
    MetodoPago,
    MovimientoCaja,
    TipoMovimientoCaja,
    TurnoCaja,
)
from app.models.cliente import Cliente
from app.models.inventario import (
    Conteo,
    Lote,
    MovimientoInventario,
    TipoMovimientoInventario,
)
from app.models.notificacion import Notificacion, TipoNotificacion
from app.models.promocion import (
    CLASES_ESTADO_PROMO,
    ETIQUETAS_ESTADO_PROMO,
    AplicacionPromocion,
    Promocion,
    PromocionProducto,
    TipoDescuento,
)
from app.models.proveedor import Insumo, Proveedor
from app.models.sistema import Auditoria, Configuracion
from app.models.usuario import RolUsuario, Usuario
from app.models.venta import (
    CLASES_ESTADO_VENTA,
    ETIQUETAS_ESTADO_VENTA,
    EstadoVenta,
    Venta,
    VentaDetalle,
)

__all__ = [
    'Usuario',
    'RolUsuario',
    'Configuracion',
    'Auditoria',
    'Cliente',
    'Proveedor',
    'Insumo',
    'Articulo',
    'ArticuloInsumo',
    'CodigoBarras',
    'Lote',
    'Conteo',
    'MovimientoInventario',
    'TipoMovimientoInventario',
    'MetodoPago',
    'TurnoCaja',
    'MovimientoCaja',
    'Arqueo',
    'EstadoTurno',
    'TipoMovimientoCaja',
    'CategoriaMovimientoCaja',
    'Venta',
    'VentaDetalle',
    'EstadoVenta',
    'ETIQUETAS_ESTADO_VENTA',
    'CLASES_ESTADO_VENTA',
    'Promocion',
    'PromocionProducto',
    'TipoDescuento',
    'AplicacionPromocion',
    'ETIQUETAS_ESTADO_PROMO',
    'CLASES_ESTADO_PROMO',
    'Notificacion',
    'TipoNotificacion',
]
