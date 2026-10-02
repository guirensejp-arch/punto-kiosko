"""Tests del cierre X (arqueo parcial) y del cierre Z."""

from app.extensions import db
from app.models.caja import EstadoTurno
from app.services import caja_service, venta_service


def test_resumen_x_no_cierra_turno(app, datos):
    turno = caja_service.abrir_turno(0, datos.admin.id)
    db.session.commit()
    venta_service.crear_venta([(datos.articulo, 2)], datos.admin.id,
                              metodo_pago=datos.metodo, turno=turno)
    db.session.commit()

    resumen = caja_service.resumen_x(turno, efectivo_contado=280000)
    assert resumen['ventas'] == 300000
    assert resumen['ventas_cantidad'] == 1
    assert resumen['diferencia'] == -20000
    # No cerró el turno.
    db.session.refresh(turno)
    assert turno.estado == EstadoTurno.ABIERTO
    assert turno.arqueo is None


def test_cierre_x_get_ok(logged_client, datos):
    from app.services import caja_service
    from app.extensions import db as _db
    caja_service.abrir_turno(0, datos.admin.id)
    _db.session.commit()
    r = logged_client.get('/caja/cierre-x')
    assert r.status_code == 200
    assert b'Cierre X' in r.data


def test_cierre_z_si_cierra(app, datos):
    turno = caja_service.abrir_turno(0, datos.admin.id)
    db.session.commit()
    # Sin ventas, el efectivo esperado es 0: cierra con diferencia 0.
    caja_service.cerrar_turno(turno, 0, datos.admin.id)
    db.session.commit()
    db.session.refresh(turno)
    assert turno.estado == EstadoTurno.CERRADO
    assert turno.arqueo is not None
