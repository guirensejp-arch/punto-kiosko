"""Tests de venta por peso (artículos pesables)."""

from decimal import Decimal

from app.extensions import db
from app.models.articulo import Articulo
from app.models.venta import Venta
from app.services import caja_service, venta_service


def _jamon(fabrica):
    return fabrica.articulo(
        nombre='Jamón cocido', precio=250000, costo=180000, categoria='Fiambres',
        stock_propio=True, stock='2.500', unidad='kg',
    )


def test_pesable_descuenta_decimal_y_cobra_proporcional(app, fabrica, datos):
    jamon = _jamon(fabrica)
    jamon.es_pesable = True
    db.session.commit()
    turno = caja_service.abrir_turno(0, datos.admin.id)
    db.session.commit()

    venta = venta_service.crear_venta(
        [(jamon, Decimal('0.250'))], datos.admin.id,
        metodo_pago=datos.metodo, pago_recibido=100000, turno=turno,
    )
    db.session.commit()

    assert venta.total == 62500  # 0.250 * 250000
    db.session.refresh(jamon)
    assert jamon.stock == Decimal('2.250')


def test_no_pesable_rechaza_decimal(app, fabrica, datos):
    import pytest
    art = fabrica.articulo(nombre='Coca', stock='10', unidad='ud')
    with pytest.raises(ValueError):
        venta_service.crear_venta(
            [(art, Decimal('0.5'))], datos.admin.id, metodo_pago=datos.metodo,
        )


def test_pos_cobra_pesable_por_json(client, login, fabrica, datos):
    jamon = _jamon(fabrica)
    jamon.es_pesable = True
    db.session.commit()
    login(email='admin@test.com')
    r = client.post('/ventas/cobrar', json={
        'lineas': [{'articulo_id': jamon.id, 'cantidad': 0.4}],
        'metodo_pago_id': datos.metodo.id,
        'pago_recibido': 100000,
    })
    assert r.status_code == 200
    assert r.get_json()['venta']['total'] == 100000  # 0.4 * 250000
