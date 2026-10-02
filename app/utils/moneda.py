"""Manejo de moneda como entero en centavos (nunca float).

Regla del proyecto: todo monto se guarda como entero de centavos. Estas
funciones convierten entre el texto que tipea el usuario (formato argentino) y
los centavos, y formatean de vuelta para mostrar.
"""

import re

CENTAVOS = 100


def parsear_centavos(valor):
    """Convierte un monto a centavos enteros.

    Acepta ``'$ 8.900'``, ``'8900'``, ``'8900,50'`` o ``'8.900,50'``
    (separador de miles con punto, decimal con coma). Lanza ``ValueError`` si
    el texto no representa un monto válido.
    """
    if valor is None or isinstance(valor, bool):
        raise ValueError('Monto inválido.')

    if isinstance(valor, int):
        return valor * CENTAVOS
    if isinstance(valor, float):
        return int(round(valor * CENTAVOS))

    texto = re.sub(r'[^\d,.]', '', str(valor).strip())
    if not texto or texto.strip('.,') == '':
        raise ValueError('Monto inválido.')

    if ',' in texto:
        entero, decimales = texto.rsplit(',', 1)
        entero = entero.replace('.', '')
    elif texto.count('.') == 1 and len(texto.split('.')[1]) <= 2:
        entero, decimales = texto.split('.')
    else:
        entero, decimales = texto.replace('.', ''), ''

    entero = entero or '0'
    decimales = (decimales + '00')[:2]
    return int(entero) * CENTAVOS + int(decimales)


def formatear_centavos(centavos):
    """Formatea centavos como ``'$ 8.900'`` (o ``'$ 8.900,50'`` si hay decimales)."""
    if centavos is None:
        return '$ 0'

    centavos = int(centavos)
    signo = '-' if centavos < 0 else ''
    entero, resto = divmod(abs(centavos), CENTAVOS)
    miles = f'{entero:,}'.replace(',', '.')
    if resto:
        return f'{signo}$ {miles},{resto:02d}'
    return f'{signo}$ {miles}'


def centavos_a_editable(centavos):
    """Convierte centavos a texto editable para un input (sin separador de miles)."""
    if centavos is None:
        return ''
    entero, resto = divmod(int(centavos), CENTAVOS)
    if resto:
        return f'{entero},{resto:02d}'
    return str(entero)
