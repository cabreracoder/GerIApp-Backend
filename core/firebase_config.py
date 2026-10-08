import firebase_admin
from firebase_admin import credentials
from django.conf import settings


def inicializar_firebase():

    # Evitar inicializar Firebase más de una vez
    if firebase_admin._apps:
        return firebase_admin.get_app()

    # Obtener las credenciales configuradas en Render
    cred = credentials.Certificate(
        settings.FIREBASE_CREDENTIALS
    )

    # Inicializar Firebase Admin SDK
    return firebase_admin.initialize_app(cred)