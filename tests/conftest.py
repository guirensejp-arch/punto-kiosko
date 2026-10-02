"""Fixtures compartidas para los tests de Punto Kiosko (app en memoria)."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app():
    aplicacion = create_app('testing')
    with aplicacion.app_context():
        db.create_all()
        yield aplicacion
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def login(client):
    def _login(email='admin@test.com', password='password123'):
        return client.post(
            '/auth/login',
            data={'email': email, 'password': password},
            follow_redirects=True,
        )

    return _login


@pytest.fixture()
def fabrica(app):
    from app.models.articulo import Articulo, CodigoBarras
    from app.models.caja import MetodoPago, TurnoCaja
    from app.models.usuario import RolUsuario, Usuario

    contador = {'n': 0}

    def _siguiente():
        contador['n'] += 1
        return contador['n']

    class Fabrica:
        def usuario(self, rol=RolUsuario.ADMIN, email=None, nombre='Test',
                    password='password123'):
            numero = _siguiente()
            email = email or f'{rol.value.lower()}{numero}@test.com'
            usuario = Usuario(nombre=nombre, apellido='Test',
                              email_personal=email, rol=rol, activo=True)
            usuario.set_password(password)
            db.session.add(usuario)
            db.session.commit()
            return usuario

        def articulo(self, nombre='Coca-Cola 500ml', precio=150000, costo=100000,
                     categoria='Bebidas', sku=None, stock_propio=True, stock='24',
                     unidad='ud'):
            articulo = Articulo(
                nombre=nombre, categoria=categoria, precio_venta=precio,
                precio_costo=costo, sku=sku, stock_propio=stock_propio,
                stock=Decimal(str(stock)), unidad=unidad,
            )
            db.session.add(articulo)
            db.session.commit()
            return articulo

        def codigo(self, articulo, codigo='7790895001234', tipo='EAN13'):
            cb = CodigoBarras(codigo=codigo, tipo=tipo, articulo_id=articulo.id)
            db.session.add(cb)
            db.session.commit()
            return cb

        def metodo_pago(self, nombre='Efectivo', es_efectivo=True):
            metodo = MetodoPago(nombre=nombre, es_efectivo=es_efectivo)
            db.session.add(metodo)
            db.session.commit()
            return metodo

        def turno(self, usuario, fondo=0):
            from app.services import caja_service
            turno = caja_service.abrir_turno(fondo, usuario.id)
            db.session.commit()
            return turno

    return Fabrica()


@pytest.fixture()
def datos(fabrica):
    from app.models.usuario import RolUsuario

    admin = fabrica.usuario(rol=RolUsuario.ADMIN, email='admin@test.com', nombre='Admin')
    articulo = fabrica.articulo()
    fabrica.codigo(articulo)
    metodo = fabrica.metodo_pago()
    return SimpleNamespace(admin=admin, articulo=articulo, metodo=metodo)


@pytest.fixture()
def logged_client(client, login, datos):
    """Cliente ya autenticado como el admin de ``datos``."""
    login(email='admin@test.com')
    return client
