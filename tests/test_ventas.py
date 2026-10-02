"""Tests del flujo de venta: cobro, stock, anulación y búsqueda por código."""

from decimal import Decimal

from app.extensions import db
from app.models.articulo import Articulo
from app.models.caja import CategoriaMovimientoCaja, EstadoTurno, TipoMovimientoCaja
from app.models.venta import EstadoVenta, Venta
from app.services import caja_service, venta_service


def test_crear_venta_descuenta_stock_y_caja(app, datos):
    turno = caja_service.abrir_turno(0, datos.admin.id)
    db.session.commit()

    venta = venta_service.crear_venta(
        [(datos.articulo, 2)], datos.admin.id,
        metodo_pago=datos.metodo, pago_recibido=400000, turno=turno,
    )
    db.session.commit()

    assert venta.total == 300000
    assert venta.vuelto == 100000
    assert venta.estado == EstadoVenta.CONFIRMADA
    db.session.refresh(datos.articulo)
    assert datos.articulo.stock == Decimal('22.000')
    assert caja_service.kpis_turno(turno)['ventas'] == 300000
    assert caja_service.kpis_turno(turno)['pedidos'] == 1


def test_venta_sin_stock_falla(app, datos):
    import pytest
    with pytest.raises(ValueError):
        venta_service.crear_venta([(datos.articulo, 999)], datos.admin.id,
                                  metodo_pago=datos.metodo)


def test_efectivo_insuficiente_falla(app, datos):
    import pytest
    with pytest.raises(ValueError):
        venta_service.crear_venta([(datos.articulo, 1)], datos.admin.id,
                                  metodo_pago=datos.metodo, pago_recibido=1)


def test_anular_revierte_stock_y_caja(app, datos):
    turno = caja_service.abrir_turno(0, datos.admin.id)
    db.session.commit()
    venta = venta_service.crear_venta([(datos.articulo, 2)], datos.admin.id,
                                      metodo_pago=datos.metodo, turno=turno)
    db.session.commit()

    venta_service.anular_venta(venta, datos.admin.id)
    db.session.commit()

    assert venta.estado == EstadoVenta.ANULADA
    db.session.refresh(datos.articulo)
    assert datos.articulo.stock == Decimal('24.000')
    # La venta (300000) y el egreso de anulación (300000) se cancelan.
    assert caja_service.kpis_turno(turno)['ventas'] == 300000
    assert caja_service.kpis_turno(turno)['egresos'] == 300000


def test_buscar_por_codigo_devuelve_match_codigo(logged_client):
    r = logged_client.get('/ventas/buscar?q=7790895001234')
    data = r.get_json()
    assert r.status_code == 200
    assert data['match'] == 'codigo'
    assert len(data['articulos']) == 1
    assert data['articulos'][0]['nombre'] == 'Coca-Cola 500ml'


def test_buscar_por_texto_no_es_match_codigo(logged_client):
    r = logged_client.get('/ventas/buscar?q=coca')
    data = r.get_json()
    assert data['match'] is None
    assert len(data['articulos']) == 1


def test_pos_cobra_end_to_end(client, login, datos, app):
    login(email='admin@test.com')
    r = client.post('/ventas/cobrar', json={
        'lineas': [{'articulo_id': datos.articulo.id, 'cantidad': 3}],
        'metodo_pago_id': datos.metodo.id,
        'pago_recibido': 500000,
    })
    assert r.status_code == 200
    assert r.get_json()['ok'] is True
    assert Venta.query.count() == 1
    # Abre turno automáticamente si no había.
    assert caja_service.turno_abierto() is not None
