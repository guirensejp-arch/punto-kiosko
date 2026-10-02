from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user


def role_required(*roles):
    """Exige que el usuario autenticado tenga uno de los roles indicados."""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Iniciá sesión para acceder a esta página.', 'warning')
                return redirect(url_for('auth.login'))

            if current_user.rol.value not in roles:
                flash('No tenés permiso para acceder a esta página.', 'danger')
                return redirect(url_for('main.index'))

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def admin_required(f):
    """Requiere rol ADMIN."""
    return role_required('ADMIN')(f)
