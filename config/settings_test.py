"""
Configuración exclusiva para pruebas automatizadas locales en memoria.
Garantiza cero conexiones a PostgreSQL/Render y neutraliza credenciales externas.
"""

import os

import cloudinary

from .settings import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

MIGRATION_MODULES = {
    'core': None,
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'geriapp-test-cache',
    }
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Neutralizar credenciales externas durante pruebas automatizadas.
os.environ['GEMINI_API_KEY'] = ''
CLOUDINARY_CLOUD_NAME = 'test-cloud-local'
CLOUDINARY_API_KEY = 'test-key-local'
CLOUDINARY_API_SECRET = 'test-secret-local'
BREVO_API_KEY = ''
N8N_API_KEY = 'test-n8n-key-local'

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True,
)


def verificar_aislamiento_bd_pruebas(databases_config):
    """
    Verifica que todas las conexiones configuradas para pruebas sean
    exclusivamente SQLite en memoria y sin host remoto.
    """
    if not databases_config:
        raise RuntimeError('DATABASES no puede estar vacío en settings_test.')

    for alias, cfg in databases_config.items():
        engine = str(cfg.get('ENGINE') or '').strip()
        host = str(cfg.get('HOST') or '').strip()
        nombre = str(cfg.get('NAME') or '').strip()

        if engine != 'django.db.backends.sqlite3':
            raise RuntimeError(
                f"Motor de BD no permitido en pruebas para '{alias}': {engine}. "
                "Solo se permite SQLite en memoria."
            )

        if host:
            raise RuntimeError(
                f"HOST remoto o externo detectado en pruebas para '{alias}': {host}."
            )

        es_memoria = (
            nombre == ':memory:'
            or 'mode=memory' in nombre
            or nombre.startswith('file:memorydb')
        )
        if not es_memoria:
            raise RuntimeError(
                f"Base de datos en disco o externa no permitida en '{alias}': {nombre}. "
                "Debe utilizarse ':memory:'."
            )


verificar_aislamiento_bd_pruebas(DATABASES)
