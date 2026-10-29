import cv2
import numpy as np
import os
import re
import subprocess
import threading
import time
from datetime import datetime

from conexion_backend import obtener_camaras_activas


# ============================================================
# CONFIGURACION INDEPENDIENTE DEL DATASET
# ============================================================

ANCHO = 640
ALTO = 480
FPS = 30
INTERVALO_CAPTURA = 3.0

CARPETA_DATASET = os.path.join(
    "dataset_posturas",
    "seleccionadas"
)

ETIQUETAS = {
    ord("1"): "ACOSTADO",
    ord("2"): "SENTADO",
    ord("3"): "DE_PIE",
    ord("4"): "SIN_PERSONA",
}

# Crear las carpetas de las cuatro categorias.
for etiqueta in ETIQUETAS.values():
    os.makedirs(
        os.path.join(CARPETA_DATASET, etiqueta),
        exist_ok=True
    )


# ============================================================
# IDENTIFICACION DE CAMARAS USB MEDIANTE FFMPEG
# ============================================================

def normalizar_identificador(valor):
    return re.sub(r"[^a-z0-9]", "", str(valor).lower())


def obtener_dispositivos_dshow():
    resultado = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-list_devices", "true",
            "-f", "dshow",
            "-i", "dummy",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    lineas = resultado.stderr.splitlines()
    dispositivos = []

    for i, linea in enumerate(lineas):
        nombre = re.search(r'"([^"]+)"\s+\(video\)', linea)

        if not nombre:
            continue

        for siguiente in lineas[i + 1:i + 4]:
            alternativa = re.search(
                r'Alternative name "([^"]+)"',
                siguiente,
            )

            if alternativa:
                dispositivos.append({
                    "nombre": nombre.group(1),
                    "alternativa": alternativa.group(1),
                })
                break

            if "(video)" in siguiente:
                break

    return dispositivos


def buscar_dispositivo_usb(identificador, dispositivos):
    if not identificador:
        return None

    objetivo = normalizar_identificador(identificador)

    for dispositivo in dispositivos:
        alternativa = normalizar_identificador(
            dispositivo["alternativa"]
        )

        if objetivo in alternativa:
            return dispositivo["alternativa"]

    return None


# ============================================================
# LECTOR DE FOTOGRAMAS
# ============================================================

class CapturaFFmpeg:
    """Lee cada camara en segundo plano y conserva el ultimo fotograma."""

    def __init__(self, dispositivo):
        self.bytes_frame = ANCHO * ALTO * 3
        self.ultimo_frame = None
        self.bloqueo = threading.Lock()
        self.primer_frame = threading.Event()
        self.detener = threading.Event()

        comando = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "dshow",
            "-video_size", f"{ANCHO}x{ALTO}",
            "-framerate", str(FPS),
            "-i", f"video={dispositivo}",
            "-vf", "fps=15",
            "-an",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "pipe:1",
        ]

        self.proceso = subprocess.Popen(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=self.bytes_frame * 2,
            creationflags=getattr(
                subprocess, "CREATE_NO_WINDOW", 0
            ),
        )

        self.hilo = threading.Thread(
            target=self._leer_continuamente,
            daemon=True,
        )
        self.hilo.start()

    def isOpened(self):
        return (
            self.proceso is not None
            and self.proceso.poll() is None
            and not self.detener.is_set()
        )

    def _leer_continuamente(self):
        try:
            while not self.detener.is_set() and self.isOpened():
                datos = bytearray()

                while len(datos) < self.bytes_frame:
                    if self.detener.is_set():
                        return

                    bloque = self.proceso.stdout.read(
                        self.bytes_frame - len(datos)
                    )

                    if not bloque:
                        return

                    datos.extend(bloque)

                frame = np.frombuffer(
                    datos, dtype=np.uint8
                ).reshape((ALTO, ANCHO, 3)).copy()

                with self.bloqueo:
                    self.ultimo_frame = frame

                self.primer_frame.set()

        except (OSError, ValueError):
            pass

    def read(self):
        # Esperar solo al primer fotograma al iniciar.
        if self.ultimo_frame is None:
            if not self.primer_frame.wait(timeout=3):
                return False, None

        with self.bloqueo:
            if self.ultimo_frame is None:
                return False, None

            return True, self.ultimo_frame.copy()

    def release(self):
        self.detener.set()

        if self.proceso is not None and self.proceso.poll() is None:
            self.proceso.terminate()

            try:
                self.proceso.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proceso.kill()
                self.proceso.wait()

        if self.proceso is not None and self.proceso.stdout:
            self.proceso.stdout.close()

        if hasattr(self, "hilo") and self.hilo.is_alive():
            self.hilo.join(timeout=2)


# ============================================================
# INICIO DEL CAPTURADOR
# ============================================================

def main():
    capturas = []
    etiqueta_actual = None
    ultima_captura = 0
    contador = 0

    try:
        print("Consultando las camaras activas de GerIApp...")
        camaras_backend = obtener_camaras_activas()

        if not camaras_backend:
            print("No se encontraron camaras activas.")
            return

        dispositivos = obtener_dispositivos_dshow()

        if not dispositivos:
            print("FFmpeg no encontro camaras de video.")
            return

        # Abrir las camaras que tengan identificador USB.
        for camara in camaras_backend:
            id_camara = camara.get("id_camara")
            identificador = camara.get(
                "identificador_dispositivo"
            )

            if not id_camara or not identificador:
                continue

            dispositivo = buscar_dispositivo_usb(
                identificador, dispositivos
            )

            if not dispositivo:
                print(
                    f"No se encontro la camara {id_camara} "
                    "por su identificador USB."
                )
                continue

            print(
                f"Abriendo camara {id_camara}: "
                f"{dispositivo}"
            )

            captura = CapturaFFmpeg(dispositivo)

            # Comprobar que FFmpeg haya iniciado.
            time.sleep(1)

            if captura.isOpened():
                capturas.append({
                    "id": id_camara,
                    "lector": captura,
                })
            else:
                captura.release()
                print(f"No se pudo abrir la camara {id_camara}.")

        if not capturas:
            print("No se pudo abrir ninguna camara.")
            return

        print("\nCAPTURADOR DE DATASET DE POSTURAS")
        print("1 = ACOSTADO")
        print("2 = SENTADO")
        print("3 = DE_PIE")
        print("4 = SIN_PERSONA")
        print("0 = Pausar la captura")
        print("Q = Salir y cerrar las camaras\n")

        while True:
            imagenes = []

            for elemento in capturas:
                correcto, frame = elemento["lector"].read()

                if not correcto:
                    raise RuntimeError(
                        f"Se perdio la camara {elemento['id']}."
                    )

                imagen = frame.copy()

                # Mostrar la etiqueta en pantalla,
                # sin escribirla sobre la imagen guardada.
                cv2.putText(
                    imagen,
                    f"Camara {elemento['id']}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                )

                imagenes.append((elemento["id"], frame, imagen))

            # Presentar las camaras lado a lado.
            pantalla = np.hstack([
                elemento[2] for elemento in imagenes
            ])

            texto = etiqueta_actual or "PAUSADO: elige una postura"
            cv2.putText(
                pantalla,
                texto,
                (10, ALTO - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 255),
                2,
            )

            cv2.imshow("Captura de dataset - GerIApp", pantalla)
            tecla = cv2.waitKey(1) & 0xFF

            if tecla in ETIQUETAS:
                etiqueta_actual = ETIQUETAS[tecla]
                ultima_captura = 0
                print(f"Categoria seleccionada: {etiqueta_actual}")

            elif tecla == ord("0"):
                etiqueta_actual = None
                print("Captura pausada.")

            elif tecla in (ord("q"), 27):
                break

            # Guardar una imagen por camara cada intervalo.
            ahora = time.time()

            if (
                etiqueta_actual is not None
                and ahora - ultima_captura >= INTERVALO_CAPTURA
            ):
                marca_tiempo = datetime.now().strftime(
                    "%Y%m%d_%H%M%S_%f"
                )

                for id_camara, frame, _ in imagenes:
                    carpeta = os.path.join(
                        CARPETA_DATASET,
                        etiqueta_actual,
                        f"camara_{id_camara}",
                    )
                    os.makedirs(carpeta, exist_ok=True)

                    ruta = os.path.join(
                        carpeta,
                        f"{marca_tiempo}_{contador:06d}.jpg",
                    )

                    if cv2.imwrite(ruta, frame):
                        print(f"Guardada: {ruta}")

                contador += 1
                ultima_captura = ahora

    except Exception as error:
        print(f"\nError en el capturador: {error}")

    finally:
        for elemento in capturas:
            elemento["lector"].release()

        cv2.destroyAllWindows()
        print("\nCapturador cerrado. Las imagenes guardadas se conservan.")


if __name__ == "__main__":
    main()
