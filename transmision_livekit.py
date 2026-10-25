import asyncio
import os
import threading

import cv2
import numpy as np
from livekit import api, rtc


class TransmisionLiveKit:
    """Publica una pista de video por cada cámara de GerIApp."""

    ANCHO = 640
    ALTO = 480
    FPS = 10

    def __init__(self):
        self.url = os.environ.get(
            "LIVEKIT_RTC_URL",
            "wss://geriapp-monitoreo-b55p3w0b.livekit.cloud",
        )
        self.api_key = os.environ.get("LIVEKIT_API_KEY")
        self.api_secret = os.environ.get("LIVEKIT_API_SECRET")

        if not self.api_key or not self.api_secret:
            raise RuntimeError(
                "Faltan LIVEKIT_API_KEY o LIVEKIT_API_SECRET."
            )

        self.loop = asyncio.new_event_loop()
        self.hilo = threading.Thread(
            target=self._ejecutar_loop,
            daemon=True,
        )
        self.iniciado = threading.Event()
        self.conexiones = {}
        self.lock = threading.Lock()

        # Conservar solamente el último fotograma pendiente por cámara.
        self.frames_pendientes = {}
        self.publicacion_programada = set()

        self.hilo.start()

        if not self.iniciado.wait(timeout=10):
            raise RuntimeError(
                "No se pudo iniciar el bucle de LiveKit."
            )

    def _ejecutar_loop(self):
        asyncio.set_event_loop(self.loop)
        self.iniciado.set()
        self.loop.run_forever()

    async def _conectar_camara(self, id_camara, id_habitacion):
        sala_nombre = f"geriapp-habitacion-{id_habitacion}"
        identidad = f"geriapp-publicador-camara-{id_camara}"

        token = (
            api.AccessToken(self.api_key, self.api_secret)
            .with_identity(identidad)
            .with_name(f"GerIApp Camara {id_camara}")
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=sala_nombre,
                    can_publish=True,
                    can_subscribe=False,
                    can_publish_data=False,
                )
            )
            .to_jwt()
        )

        sala = rtc.Room()

        try:
            await sala.connect(self.url, token)

            fuente = rtc.VideoSource(self.ANCHO, self.ALTO)
            pista = rtc.LocalVideoTrack.create_video_track(
                f"camara-{id_camara}",
                fuente,
            )

            opciones = rtc.TrackPublishOptions(
                source=rtc.TrackSource.SOURCE_CAMERA,
                video_encoding=rtc.VideoEncoding(
                    max_bitrate=1_000_000,
                    max_framerate=self.FPS,
                ),
            )

            await sala.local_participant.publish_track(
                pista,
                opciones,
            )

            self.conexiones[int(id_camara)] = {
                "sala": sala,
                "fuente": fuente,
                "habitacion": int(id_habitacion),
            }

            print(
                f"[LiveKit] Camara {id_camara} publicada "
                f"en {sala_nombre}."
            )

        except Exception:
            await sala.disconnect()
            raise

    def iniciar_camara(self, id_camara, id_habitacion):
        futuro = asyncio.run_coroutine_threadsafe(
            self._conectar_camara(
                int(id_camara),
                int(id_habitacion),
            ),
            self.loop,
        )
        futuro.result(timeout=30)

    
    def publicar_frame(self, id_camara, frame):
        """Publica el fotograma más reciente sin acumular imágenes antiguas."""
        id_camara = int(id_camara)

        if frame is None:
            return

        with self.lock:
            conexion = self.conexiones.get(id_camara)

        if conexion is None:
            return

        imagen = cv2.resize(
            frame,
            (self.ANCHO, self.ALTO),
        )
        imagen_rgba = cv2.cvtColor(
            imagen,
            cv2.COLOR_BGR2RGBA,
        )
        imagen_rgba = np.ascontiguousarray(imagen_rgba)

        fotograma = rtc.VideoFrame(
            self.ANCHO,
            self.ALTO,
            rtc.VideoBufferType.RGBA,
            imagen_rgba.tobytes(),
        )

        # Guardar el último fotograma, reemplazando cualquier pendiente.
        with self.lock:
            self.frames_pendientes[id_camara] = fotograma

            # Solo programar una llamada pendiente por cámara.
            if id_camara in self.publicacion_programada:
                return

            self.publicacion_programada.add(id_camara)

        try:
            self.loop.call_soon_threadsafe(
                self._publicar_fotograma_pendiente,
                id_camara,
            )
        except RuntimeError:
            with self.lock:
                self.publicacion_programada.discard(id_camara)
                self.frames_pendientes.pop(id_camara, None)

    def _publicar_fotograma_pendiente(self, id_camara):
        """Entrega a LiveKit el último fotograma pendiente de la cámara."""
        with self.lock:
            conexion = self.conexiones.get(id_camara)
            fotograma = self.frames_pendientes.pop(id_camara, None)
            self.publicacion_programada.discard(id_camara)

        if conexion is None or fotograma is None:
            return

        try:
            conexion["fuente"].capture_frame(fotograma)
        except Exception as error:
            print(
                f"[LiveKit] Error publicando cámara "
                f"{id_camara}: {error}"
            )

    async def _cerrar_conexiones(self):
        for conexion in list(self.conexiones.values()):
            try:
                await conexion["sala"].disconnect()
            except Exception as error:
                print("[LiveKit] Error al cerrar sala:", error)

        self.conexiones.clear()

    def cerrar(self):
        if not self.loop.is_running():
            return

        futuro = asyncio.run_coroutine_threadsafe(
            self._cerrar_conexiones(),
            self.loop,
        )

        try:
            futuro.result(timeout=15)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.hilo.join(timeout=5)
            print("[LiveKit] Transmisiones cerradas.")
