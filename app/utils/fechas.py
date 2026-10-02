"""Conversión de fechas: se guardan en UTC y se muestran en hora de Argentina.

Argentina usa UTC-3 de forma fija (sin horario de verano desde 2009), así que se
usa un offset fijo y no se depende de la base IANA de zonas horarias (que en
Windows no viene incluida).
"""

from datetime import datetime, timedelta, timezone

ZONA_NEGOCIO = timezone(timedelta(hours=-3))  # America/Argentina/Buenos_Aires


def a_local(valor):
    """Convierte un datetime UTC (naive) a hora de Argentina.

    Si ``valor`` es None o no es datetime, lo devuelve tal cual. Los datetimes
    sin tzinfo se asumen UTC (así se persisten en el proyecto).
    """
    if valor is None or not isinstance(valor, datetime):
        return valor
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(ZONA_NEGOCIO)


def formatear_local(valor, formato='%d/%m/%Y %H:%M'):
    """Devuelve la fecha/hora local formateada, o '' si no hay valor."""
    if valor is None:
        return ''
    return a_local(valor).strftime(formato)
