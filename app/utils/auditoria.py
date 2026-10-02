"""Registro de auditoría para acciones sensibles."""

from flask_login import current_user

from app.extensions import db
from app.models.sistema import Auditoria


def registrar(accion, entidad, entidad_id=None, detalles=None):
    """Guarda una fila de auditoría. Requiere un usuario autenticado."""
    if not current_user.is_authenticated:
        return None

    registro = Auditoria(
        usuario_id=current_user.id,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        detalles=detalles,
    )
    db.session.add(registro)
    db.session.commit()
    return registro
