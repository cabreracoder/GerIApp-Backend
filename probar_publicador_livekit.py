import asyncio
import os
from livekit import api, rtc

URL = "wss://geriapp-monitoreo-b55p3w0b.livekit.cloud"
SALA = "geriapp-habitacion-1"

async def main():
    cliente = None
    sala = rtc.Room()

    try:
        token = (
            api.AccessToken(
                os.environ["LIVEKIT_API_KEY"],
                os.environ["LIVEKIT_API_SECRET"],
            )
            .with_identity("geriapp-publicador-camara-1")
            .with_name("GerIApp Camara 1")
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=SALA,
                    can_publish=True,
                    can_subscribe=False,
                    can_publish_data=False,
                )
            )
            .to_jwt()
        )

        print("Conectando a LiveKit...")
        await sala.connect(URL, token)
        print("Conexion con LiveKit: CORRECTA")
        print("Sala:", SALA)
        print("Identidad:", sala.local_participant.identity)

    except Exception as error:
        print("Error de conexion:", type(error).__name__)
        print(str(error)[:500])

    finally:
        try:
            await sala.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())
