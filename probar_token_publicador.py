import os
from livekit import api

def main():
    api_key = os.environ.get("LIVEKIT_API_KEY")
    api_secret = os.environ.get("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        print("ERROR: faltan las variables de entorno de LiveKit.")
        return

    token = (
        api.AccessToken(api_key, api_secret)
        .with_identity("geriapp-publicador-camara-1")
        .with_name("GerIApp Camara 1")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room="geriapp-habitacion-1",
                can_publish=True,
                can_subscribe=False,
                can_publish_data=False,
            )
        )
        .to_jwt()
    )

    print("Token de publicación generado correctamente.")
    print("Identidad: geriapp-publicador-camara-1")
    print("Sala: geriapp-habitacion-1")
    print("Permisos: publicar video, sin suscripción.")
    print("El token no se mostrará por seguridad.")

if __name__ == "__main__":
    main()
