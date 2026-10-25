import asyncio
import os
from livekit import api


async def main():
    cliente = None

    try:
        cliente = api.LiveKitAPI(
            url=os.environ["LIVEKIT_URL"],
            api_key=os.environ["LIVEKIT_API_KEY"],
            api_secret=os.environ["LIVEKIT_API_SECRET"],
        )

        resultado = await cliente.room.list_rooms(
            api.ListRoomsRequest()
        )

        print("Conexion con LiveKit: CORRECTA")
        print("Salas encontradas:", len(resultado.rooms))

    except Exception as error:
        print("Tipo de error:", type(error).__name__)
        print("Mensaje:", str(error)[:500])

    finally:
        if cliente is not None:
            await cliente.aclose()


if __name__ == "__main__":
    asyncio.run(main())
