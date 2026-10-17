from firebase_admin import messaging
from core.firebase_config import inicializar_firebase

from .models import FcmTokens, NotificacionDestinatario


def enviar_notificacion_fcm(notificacion, usuario):

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
        print(
            f"FCM: El usuario {usuario.pk} "
            "no tiene tokens activos."
        )
        return

    try:
        app = inicializar_firebase()

        if app is None:
            print("FCM: Firebase no pudo inicializarse.")
            return

    except Exception as error:
        print(f"FCM: Error inicializando Firebase: {error}")
        return

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
            print(f"FCM enviado correctamente: {respuesta}")

        except Exception as error:
            print(
                f"FCM: Error enviando al token "
                f"{fcm_token.id_fcm_token}: {error}"
            )