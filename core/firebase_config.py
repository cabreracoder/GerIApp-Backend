import os

import firebase_admin
from firebase_admin import credentials
from django.conf import settings


def inicializar_firebase():

    # Evitar inicializar Firebase más de una vez
    if firebase_admin._apps:
        return firebase_admin.get_app()

    ruta_credenciales = settings.FIREBASE_CREDENTIALS

    # Firebase solo se inicializa si las credenciales existen
    if not ruta_credenciales:
        print(
            "GERIAPP_FIREBASE: FIREBASE_CREDENTIALS no está configurado."
        )
        return None

    if not os.path.exists(ruta_credenciales):
        print(
            f"GERIAPP_FIREBASE: no se encontró el archivo de credenciales: "
            f"{ruta_credenciales}"
        )
        return None

    cred = credentials.Certificate(ruta_credenciales)

    return firebase_admin.initialize_app(cred)