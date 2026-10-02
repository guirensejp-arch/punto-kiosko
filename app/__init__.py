from flask import Flask, redirect, render_template, request, url_for

from app.extensions import csrf, db, login_manager, migrate
from config import config


def create_app(config_name='default'):
    """Application factory: arma la app, inicializa extensiones y blueprints."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Importar modelos registra el esquema en SQLAlchemy (necesario para migraciones).
    from app import models  # noqa: F401

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # Marca (nombre, logo, colores): expone `branding` a todos los templates.
    from app.utils.branding import init_branding

    init_branding(app)

    # Blueprints por módulo.
    from app.blueprints.analitica import analitica_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.caja import caja_bp
    from app.blueprints.insumos import insumos_bp
    from app.blueprints.inventario import inventario_bp
    from app.blueprints.main import main_bp
    from app.blueprints.ventas import ventas_bp
    from app.blueprints.promociones import promociones_bp
    from app.blueprints.proveedores import proveedores_bp
    from app.blueprints.articulos import articulos_bp
    from app.blueprints.sistema import sistema_bp
    from app.blueprints.usuarios import usuarios_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(sistema_bp)
    app.register_blueprint(usuarios_bp)
    app.register_blueprint(proveedores_bp)
    app.register_blueprint(insumos_bp)
    app.register_blueprint(articulos_bp)
    app.register_blueprint(inventario_bp)
    app.register_blueprint(caja_bp)
    app.register_blueprint(ventas_bp)
    app.register_blueprint(promociones_bp)
    app.register_blueprint(analitica_bp)

    _registrar_filtros(app)
    _registrar_contexto(app)
    _registrar_estado_shell(app)

    # Comandos de CLI (flask crear-admin).
    from app import cli

    cli.init_app(app)

    _registrar_manejo_sesion(app)
    _registrar_paginas_error(app)

    return app


def _registrar_filtros(app):
    """Filtros/globales de Jinja para moneda y costos."""
    from app.services.food_cost import costo_linea, costo_producto, margen_producto
    from app.services.inventario_service import (
        CLASES_ESTADO,
        ESTADO_OK,
        ESTADO_POR_VENCER,
        ESTADO_VENCIDA,
        ETIQUETAS_ESTADO,
        estado_lote,
        stock_insumo,
    )
    from app.services.phone_normalizer import formatear_telefono
    from app.utils.moneda import centavos_a_editable, formatear_centavos
    from app.models.venta import CLASES_ESTADO_VENTA, ETIQUETAS_ESTADO_VENTA
    from app.models.promocion import CLASES_ESTADO_PROMO, ETIQUETAS_ESTADO_PROMO

    app.jinja_env.filters['moneda'] = formatear_centavos
    app.jinja_env.filters['centavos_editable'] = centavos_a_editable
    app.jinja_env.filters['telefono'] = formatear_telefono
    app.jinja_env.globals.update(
        costo_linea=costo_linea,
        costo_producto=costo_producto,
        margen_producto=margen_producto,
        estado_lote=estado_lote,
        stock_insumo=stock_insumo,
        etiquetas_estado=ETIQUETAS_ESTADO,
        clases_estado=CLASES_ESTADO,
        estado_ok=ESTADO_OK,
        estado_por_vencer=ESTADO_POR_VENCER,
        estado_vencida=ESTADO_VENCIDA,
        etiquetas_pedido=ETIQUETAS_ESTADO_VENTA,
        clases_pedido=CLASES_ESTADO_VENTA,
        etiquetas_promo=ETIQUETAS_ESTADO_PROMO,
        clases_promo=CLASES_ESTADO_PROMO,
    )


def _registrar_contexto(app):
    """Expone la configuración global (tema, tamaño de fuente) a los templates."""

    @app.context_processor
    def injectar_configuracion():
        from app.models.sistema import Configuracion

        return {'configuracion': Configuracion.get()}


def _registrar_estado_shell(app):
    """Datos de solo lectura para la barra superior (turno y pendientes).

    No modifica rutas ni modelos: solo agrega contexto para el shell. Es
    defensivo a propósito, para que un error de consulta nunca rompa una página.
    """

    @app.context_processor
    def inyectar_estado_shell():
        from flask_login import current_user

        estado = {'turno_actual': None}

        if not current_user.is_authenticated or request.endpoint == 'static':
            return estado

        try:
            from app.services.caja_service import turno_abierto

            estado['turno_actual'] = turno_abierto()
        except Exception:  # pragma: no cover - nunca romper el shell
            db.session.rollback()

        return estado


def _registrar_manejo_sesion(app):
    """Fuerza el cambio de contraseña en el próximo login tras un reset."""

    @app.before_request
    def forzar_cambio_clave():
        from flask_login import current_user

        if not current_user.is_authenticated:
            return None

        if not current_user.debe_cambiar_clave:
            return None

        endpoints_permitidos = {'auth.cambiar_password', 'auth.logout', 'static'}
        if request.endpoint in endpoints_permitidos:
            return None

        return redirect(url_for('auth.cambiar_password'))


def _registrar_paginas_error(app):
    @app.errorhandler(404)
    def no_encontrado(error):
        return render_template('errores/404.html'), 404

    @app.errorhandler(500)
    def error_interno(error):
        db.session.rollback()
        return render_template('errores/500.html'), 500
