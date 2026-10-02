"""Normalización de teléfonos (regla 9.3 del doc de articulo).

Guarda SIEMPRE el mismo formato canónico para evitar duplicados silenciosos:
``+549`` + 10 dígitos (código de área + número).
"""

import re

PREFIJO = '+549'


def normalize_phone(raw):
    """Devuelve el teléfono en formato canónico o ``None`` si no hay dígitos.

    Acepta variantes como ``11 1234 5678``, ``011-1234-5678``,
    ``+54 9 11 1234 5678`` o ``+54 11 1234 5678``.
    """
    if not raw:
        return None

    digitos = re.sub(r'\D', '', str(raw))
    if not digitos:
        return None

    if digitos.startswith('54'):
        digitos = digitos[2:]

    digitos = digitos.lstrip('0')

    # El marcador "15" aparece después del código de área; si sobra longitud,
    # se elimina para quedarnos con área + número.
    if len(digitos) > 10:
        posicion = digitos.find('15')
        if posicion > 0:
            digitos = digitos[:posicion] + digitos[posicion + 2:]

    ultimos = digitos[-10:] if len(digitos) >= 10 else digitos
    return f'{PREFIJO}{ultimos}'


def formatear_telefono(telefono):
    """Muestra un teléfono canónico de forma legible: ``+54 9 11 1234-5678``."""
    if not telefono:
        return ''
    digitos = re.sub(r'\D', '', telefono)
    if len(digitos) == 13 and digitos.startswith('549'):
        return f'+54 9 {digitos[3:5]} {digitos[5:9]}-{digitos[9:13]}'
    return telefono
