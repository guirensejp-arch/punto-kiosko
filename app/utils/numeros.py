"""Parseo de números decimales tipeados por el usuario.

Acepta tanto el formato argentino (coma decimal: ``3,2``) como el punto
decimal (``3.2``) e ignorando separadores de miles.
"""

from decimal import Decimal, InvalidOperation


def parsear_decimal(valor):
    """Convierte un texto a ``Decimal``. Devuelve ``None`` si viene vacío.

    Lanza ``ValueError`` si el texto no es un número válido.
    """
    if valor is None:
        return None

    texto = str(valor).strip().replace(' ', '')
    if not texto:
        return None

    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    # else: se asume punto decimal (o entero)

    try:
        return Decimal(texto)
    except InvalidOperation as error:
        raise ValueError(f'Número inválido: {valor!r}') from error
