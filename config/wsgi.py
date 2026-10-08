"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os
import logging

from django.core.wsgi import get_wsgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings"
)

application = get_wsgi_application()

# Comprobación temporal de Firebase
logger = logging.getLogger(__name__)

try:
    from core.firebase_config import inicializar_firebase

    inicializar_firebase()

    logger.warning(
        "GERIAPP_FIREBASE: inicialización correcta"
    )

except Exception:
    logger.exception(
        "GERIAPP_FIREBASE: error al inicializar Firebase"
    )


#import os

#from django.core.wsgi import get_wsgi_application

#os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

#application = get_wsgi_application()
