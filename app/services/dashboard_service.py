"""Agregados del Dashboard: KPIs y rankings por período."""

from datetime import date, datetime, time, timedelta

from app.models.venta import EstadoVenta, Venta
from app.models.articulo import Articulo
from app.services.food_cost import margen_producto

PERIODOS = {
    'DIA': 'Día',
    'SEMANA': 'Semana',
    'MES': 'Mes',
    'HISTORICO': 'Histórico',
}

_DIAS = {'DIA': 1, 'SEMANA': 7, 'MES': 30}


def resumen(periodo='DIA'):
    desde = None
    if periodo in _DIAS:
        desde = datetime.combine(date.today() - timedelta(days=_DIAS[periodo] - 1), time.min)

    consulta = Venta.query.filter(Venta.estado != EstadoVenta.ANULADA)
    if desde is not None:
        consulta = consulta.filter(Venta.fecha_hora >= desde)
    ventas = consulta.all()

    ventas = sum(venta.total for venta in ventas)
    cantidad = len(ventas)
    ticket_promedio = round(ventas / cantidad) if cantidad else 0

    articulos = Articulo.query.filter_by(activo=True).all()
    conteos = {articulo.id: 0 for articulo in articulos}
    for venta in ventas:
        for detalle in venta.detalles:
            if detalle.articulo_id in conteos:
                conteos[detalle.articulo_id] += detalle.cantidad

    ranking = [
        {'articulo': articulo, 'cantidad': conteos[articulo.id]}
        for articulo in articulos
    ]

    mayor_margen = None
    for articulo in articulos:
        margen = margen_producto(articulo)
        if margen is not None and (mayor_margen is None or margen > mayor_margen[1]):
            mayor_margen = (articulo, margen)

    return {
        'ventas': ventas,
        'ventas': cantidad,
        'ticket_promedio': ticket_promedio,
        'mas_vendidos': sorted(ranking, key=lambda f: f['cantidad'], reverse=True)[:5],
        'menos_vendidos': sorted(ranking, key=lambda f: f['cantidad'])[:5],
        'mayor_margen': mayor_margen,
    }
