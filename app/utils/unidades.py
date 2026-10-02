"""Conversión de unidades de medida (kg↔g, l↔ml, ud).

Permite sumar en un mismo costo insumos cargados en unidades distintas.
"""

from decimal import Decimal

# unidad -> (familia, cuántas unidades base contiene 1 de esta unidad)
FACTORES = {
    'kg': ('masa', Decimal('1000')),
    'g': ('masa', Decimal('1')),
    'l': ('volumen', Decimal('1000')),
    'ml': ('volumen', Decimal('1')),
    'ud': ('unidad', Decimal('1')),
}

UNIDADES = tuple(FACTORES.keys())


def normalizar_unidad(unidad):
    return (unidad or '').strip().lower()


def son_compatibles(desde, hacia):
    """True si ambas unidades pertenecen a la misma familia (masa/volumen/unidad)."""
    origen = FACTORES.get(normalizar_unidad(desde))
    destino = FACTORES.get(normalizar_unidad(hacia))
    return bool(origen and destino and origen[0] == destino[0])


def convertir(cantidad, desde, hacia):
    """Convierte ``cantidad`` de ``desde`` a ``hacia``.

    Devuelve un ``Decimal`` o ``None`` si las unidades no son compatibles.
    """
    origen = FACTORES.get(normalizar_unidad(desde))
    destino = FACTORES.get(normalizar_unidad(hacia))
    if not origen or not destino or origen[0] != destino[0]:
        return None
    return Decimal(str(cantidad)) * origen[1] / destino[1]
