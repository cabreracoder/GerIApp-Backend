import asyncio
import os
import time

import cv2
import numpy as np
from livekit import api, rtc

URL = "wss://geriapp-monitoreo-b55p3w0b.livekit.cloud"
SALA = "geriapp-habitacion-1"
ANCHO = 640
ALTO = 480
FPS = 15
DURACION = 10


async def main():
    sala = rtc.Room()
    fuente = None

    try:
        token = (
            api.AccessToken(
                os.environ["LIVEKIT_API_KEY"],
                os.environ["LIVEKIT_API_SECRET"],
            )
            .with_identity("geriapp-publicador-camara-1")
            .with_name("Prueba de video GerIApp")
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

        fuente = rtc.VideoSource(ANCHO, ALTO)
        pista = rtc.LocalVideoTrack.create_video_track(
            "camara-1",
            fuente,
        )

        opciones = rtc.TrackPublishOptions(
            source=rtc.TrackSource.SOURCE_CAMERA,
            video_encoding=rtc.VideoEncoding(
                max_bitrate=1_000_000,
                max_framerate=FPS,
            ),
        )

        await sala.local_participant.publish_track(pista, opciones)
        print("Video publicado correctamente.")
        print(f"Sala: {SALA}")
        print(f"Transmitiendo durante {DURACION} segundos...")

        inicio = time.monotonic()
        fotogramas = 0

        while time.monotonic() - inicio < DURACION:
            imagen = np.zeros((ALTO, ANCHO, 4), dtype=np.uint8)
            imagen[:, :, 0] = 25
            imagen[:, :, 1] = 70
            imagen[:, :, 2] = 130
            imagen[:, :, 3] = 255

            cv2.putText(
                imagen,
                "GERIAPP - LIVEKIT",
                (50, 180),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.1,
                (255, 255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                imagen,
                f"Fotograma: {fotogramas}",
                (50, 240),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            fotograma = rtc.VideoFrame(
                ANCHO,
                ALTO,
                rtc.VideoBufferType.RGBA,
                imagen.tobytes(),
            )
            fuente.capture_frame(fotograma)
            fotogramas += 1
            await asyncio.sleep(1 / FPS)

        print("Prueba terminada.")
        print("Fotogramas enviados:", fotogramas)

    except Exception as error:
        print("Error:", type(error).__name__)
        print(str(error)[:500])

    finally:
        try:
            await sala.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
