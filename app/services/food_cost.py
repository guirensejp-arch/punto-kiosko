"""Cálculo de food cost y margen (derivados, nunca persistidos).

El food cost se recalcula en vivo: si cambia el costo de un insumo, las recetas
que lo usan reflejan el nuevo valor sin guardar datos duplicados.
"""

from decimal import Decimal

from app.utils.unidades import convertir


def costo_linea(linea):
    """Costo en centavos de una línea de receta (cantidad × costo unitario)."""
    if linea.insumo is None:
        return 0

    cantidad = convertir(linea.cantidad, linea.unidad, linea.insumo.unidad)
    if cantidad is None:
        # Unidad incompatible: no debería ocurrir (se valida al guardar).
        cantidad = Decimal(str(linea.cantidad))

    return int(round(cantidad * Decimal(linea.insumo.costo)))


def costo_producto(articulo):
    """Costo del artículo en centavos.

    Para artículos de reventa (``stock_propio``) o sin insumos, es el
    ``precio_costo`` cargado. Para elaborados, es la suma de sus insumos.
    """
    if articulo.stock_propio or not articulo.insumos:
        return int(articulo.precio_costo or 0)
    return sum(costo_linea(linea) for linea in articulo.insumos)


def margen_producto(articulo):
    """Margen bruto en porcentaje entero, o ``None`` si el precio es 0."""
    if not articulo.precio_venta:
        return None
    costo = costo_producto(articulo)
    return round((articulo.precio_venta - costo) * 100 / articulo.precio_venta)
