"""Tests de inventario, ingreso de mercadería, import y remarcado."""

import io

from app.extensions import db
from app.models.articulo import Articulo, CodigoBarras
from app.services.inventario_service import stock_insumo
from app.models.inventario import MovimientoInventario


def test_ingreso_por_codigo_suma_stock(logged_client, datos):
    r = logged_client.post('/inventario/ingreso', data={
        'codigo': '7790895001234', 'cantidad': '6', 'direccion': 'sumar',
    })
    assert r.status_code == 200
    db.session.refresh(datos.articulo)
    assert float(datos.articulo.stock) == 30.0
    assert MovimientoInventario.query.count() == 1


def test_ingreso_codigo_inexistente_no_rompe(logged_client, datos):
    r = logged_client.post('/inventario/ingreso', data={
        'codigo': '0000000000', 'cantidad': '1', 'direccion': 'sumar',
    })
    assert r.status_code == 200
    assert b'Sin art' in r.data


def test_import_articulos_csv(logged_client, datos):
    csv = (
        'nombre,categoria,sku,codigo_barras,precio_venta,precio_costo,stock,unidad,stock_propio\n'
        'Alfajor,Golosinas,ALF1,7791234567890,600,400,30,ud,si\n'
    )
    data = {'archivo': (io.BytesIO(csv.encode('utf-8')), 'arts.csv')}
    r = logged_client.post('/articulos/importar', data=data,
                           content_type='multipart/form-data')
    assert r.status_code == 200
    art = Articulo.query.filter_by(sku='ALF1').first()
    assert art is not None
    assert art.precio_venta == 60000
    assert CodigoBarras.query.filter_by(codigo='7791234567890').first() is not None


def test_remarcar_porcentaje(logged_client, datos):
    r = logged_client.post('/articulos/remarcar', data={
        'modo': 'PORCENTAJE', 'valor': '10', 'categoria': 'Bebidas', 'aplicar': '1',
    })
    assert r.status_code in (200, 302)
    db.session.refresh(datos.articulo)
    assert datos.articulo.precio_venta == 165000  # 150000 * 1.10


def test_inventario_muestra_articulos_reventa(logged_client, datos):
    r = logged_client.get('/inventario/')
    assert r.status_code == 200
    assert 'Artículos de reventa'.encode('utf-8') in r.data
