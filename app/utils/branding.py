"""Carga del branding white-label desde branding.yaml (Día 0)."""

import yaml
from flask import current_app

_DEFAULTS = {
    'negocio': {
        'nombre': 'Comanda',
        'emoji': '',
        'orden': 'nombre_logo',
        'logo': 'branding/logo_cliente.svg',
        'favicon': 'branding/logo_cliente.svg',
    },
    'leudar': {
        'nombre': 'LeudAr Labs',
        'articulo': 'Comanda',
        'logo': 'branding/logo_leudar.svg',
        'marca_agua': True,
    },
    'colores': {
        'primario': '#263238',
        'secundario': '#e65100',
        'acento': '#f9a825',
        'fondo': '#eceff1',
    },
    'footer': {
        'texto': '',
    },
}


def _merge(base, override):
    """Combina recursivamente el branding cargado sobre los valores por defecto."""
    resultado = dict(base)
    for clave, valor in (override or {}).items():
        if isinstance(valor, dict) and isinstance(resultado.get(clave), dict):
            resultado[clave] = _merge(resultado[clave], valor)
        else:
            resultado[clave] = valor
    return resultado


def cargar_branding():
    """Lee branding.yaml y lo devuelve completo (con defaults si falta algo)."""
    ruta = current_app.config.get('BRANDING_FILE')
    try:
        with open(ruta, 'r', encoding='utf-8') as archivo:
            datos = yaml.safe_load(archivo) or {}
    except (OSError, yaml.YAMLError):
        datos = {}
    return _merge(_DEFAULTS, datos)


def init_branding(app):
    """Expone `branding` en todos los templates vía context processor."""

    @app.context_processor
    def injectar_branding():
        return {'branding': cargar_branding()}
