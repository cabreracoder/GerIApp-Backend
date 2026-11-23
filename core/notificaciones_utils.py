from firebase_admin import messaging
from core.firebase_config import inicializar_firebase

from .models import FcmTokens, NotificacionDestinatario



def enviar_notificacion_fcm(notificacion, usuario):

    resultado = {
        "exito": False,
        "enviados": 0,
        "fallidos": 0,
        "sin_tokens": False,
        "error": None
    }

    # Registrar destinatario sin duplicarlo.
    NotificacionDestinatario.objects.get_or_create(
        id_notificacion=notificacion,
        id_usuario=usuario,
        defaults={
            "leida": False,
            "fecha_lectura": None
        }
    )

    tokens = FcmTokens.objects.filter(
        id_usuario=usuario,
        activo=True
    )

    if not tokens.exists():
        resultado["sin_tokens"] = True
        resultado["error"] = "El usuario no tiene tokens FCM activos."
        print(f"FCM: {resultado['error']} Usuario: {usuario.pk}")
        return resultado

    try:
        app = inicializar_firebase()

        if app is None:
            resultado["error"] = "Firebase no pudo inicializarse."
            print(f"FCM: {resultado['error']}")
            return resultado

    except Exception as error:
        resultado["error"] = str(error)
        print(f"FCM: Error inicializando Firebase: {error}")
        return resultado

    for fcm_token in tokens:

        mensaje = messaging.Message(
            notification=messaging.Notification(
                title=notificacion.titulo,
                body=notificacion.mensaje
            ),
            data={
                "id_notificacion": str(
                    notificacion.id_notificacion
                ),
                "tipo": str(notificacion.tipo or "")
            },
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="geriapp_notificaciones"
                )
            ),
            token=fcm_token.token
        )

        try:
            respuesta = messaging.send(mensaje)

            resultado["enviados"] += 1

            print(f"FCM enviado correctamente: {respuesta}")

        except Exception as error:
            resultado["fallidos"] += 1

            print(
                f"FCM: Error enviando al token "
                f"{fcm_token.id_fcm_token}: {error}"
            )

    resultado["exito"] = resultado["enviados"] > 0

    if not resultado["exito"]:
        resultado["error"] = "No se pudo enviar a ningún token FCM."

    return resultado
