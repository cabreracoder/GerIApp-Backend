
import threading
import time
import os
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np


MAX_BYTES_IMAGEN = 8 * 1024 * 1024


def iniciar_receptor(
    estados,
    camaras_config,
    host="0.0.0.0",
    puerto=8000,
):
    """
    Recibe fotogramas JPEG enviados desde Windows.

    Ruta:
        POST /frame/<id_camara>

    El ID corresponde al identificador de la cámara
    registrado en GerIApp.
    """
    token_recepcion = os.getenv(
        "GERIAPP_FRAME_TOKEN",
        ""
    ).strip()

    if not token_recepcion:
        raise RuntimeError(
            "No está configurado GERIAPP_FRAME_TOKEN."
        )

    # Relacionar el ID de GerIApp con el nombre interno
    # utilizado por el monitor.
    mapa_camaras = {}

    for nombre, config in camaras_config.items():

        id_camara = config.get("id_camara")

        if id_camara is not None:
            mapa_camaras[str(id_camara)] = nombre

    class ReceptorFramesHandler(BaseHTTPRequestHandler):

        protocol_version = "HTTP/1.1"

        def responder(self, codigo, mensaje):

            cuerpo = mensaje.encode("utf-8")

            self.send_response(codigo)
            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8"
            )
            self.send_header(
                "Content-Length",
                str(len(cuerpo))
            )
            self.send_header("Connection", "close")
            self.end_headers()

            self.wfile.write(cuerpo)
            self.close_connection = True

        def do_GET(self):

            if self.path == "/health":
                self.responder(
                    200,
                    "Receptor de fotogramas activo"
                )
                return

            self.responder(404, "Ruta no encontrada")

        def do_POST(self):

            token_recibido = self.headers.get(
                "X-Frame-Token",
                ""
            ).strip()

            if not hmac.compare_digest(
                token_recibido,
                token_recepcion
            ):
                self.responder(
                    401,
                    "No autorizado"
                )
                return

            partes = self.path.strip("/").split("/")

            if len(partes) != 2 or partes[0] != "frame":
                self.responder(404, "Ruta no encontrada")
                return

            id_camara = partes[1]

            nombre = mapa_camaras.get(id_camara)

            if nombre is None:
                self.responder(
                    404,
                    "ID de cámara no configurado"
                )
                return

            try:
                longitud = int(
                    self.headers.get("Content-Length", "0")
                )
            except ValueError:
                self.responder(
                    400,
                    "Content-Length inválido"
                )
                return

            if longitud <= 0 or longitud > MAX_BYTES_IMAGEN:
                self.responder(
                    413,
                    "Tamaño de imagen no permitido"
                )
                return

            try:

                datos = self.rfile.read(longitud)

                if len(datos) != longitud:
                    self.responder(
                        400,
                        "Imagen incompleta"
                    )
                    return

                imagen = cv2.imdecode(
                    np.frombuffer(
                        datos,
                        dtype=np.uint8
                    ),
                    cv2.IMREAD_COLOR
                )

                if imagen is None:
                    self.responder(
                        400,
                        "No se pudo decodificar la imagen"
                    )
                    return

                estado = estados.get(nombre)

                if estado is None:
                    self.responder(
                        404,
                        "Estado de cámara no encontrado"
                    )
                    return

                with estado["frame_lock"]:

                    estado["frame"] = imagen
                    estado["frame_seq"] = (
                        estado.get("frame_seq", 0) + 1
                    )
                    estado["activa"] = True
                    estado["ultima_recepcion"] = time.time()

                self.responder(
                    200,
                    "Fotograma recibido"
                )

            except (BrokenPipeError, ConnectionResetError):
                pass

            except Exception as error:

                print(
                    f"[RECEPTOR] Error recibiendo imagen: {error}"
                )

                try:
                    self.responder(
                        500,
                        "Error interno"
                    )
                except OSError:
                    pass

        def log_message(self, formato, *argumentos):
            print(
                f"[HTTP] {self.client_address[0]} - "
                f"{formato % argumentos}",
                flush=True
            )

    servidor = ThreadingHTTPServer(
        (host, puerto),
        ReceptorFramesHandler
    )

    servidor.daemon_threads = True

    hilo = threading.Thread(
        target=servidor.serve_forever,
        name="ReceptorFrames",
        daemon=True
    )

    hilo.start()

    print(
        f"[RECEPTOR] Escuchando en http://{host}:{puerto}"
    )

    print(
        f"[RECEPTOR] Cámaras configuradas: {len(mapa_camaras)}"
    )

    return servidor, hilo
