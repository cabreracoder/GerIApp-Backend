
import os

import cv2
import requests
import threading
import time


# ----------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------

URL_RECEPTOR = "https://vd45r1h16evzi4-8000.proxy.runpod.net"

TOKEN_RECEPTOR = os.getenv(
    "GERIAPP_FRAME_TOKEN",
    ""
).strip()
# Formato:
# ID de cámara GerIApp: índice físico OpenCV.
#
# IMPORTANTE:
# Verificar los ID reales de obtener_camaras_activas()
# antes de iniciar la transmisión.

CAMARAS = {
    1: 1,
    2: 2,
}

ANCHO = 640
ALTO = 480
FPS = 15
CALIDAD_JPEG = 75

EJECUTANDO = threading.Event()
EJECUTANDO.set()


# ----------------------------------------------------
# CAPTURA Y TRANSMISIÓN
# ----------------------------------------------------

def transmitir_camara(id_camara, indice_opencv):

    sesion = requests.Session()

    url = f"{URL_RECEPTOR}/frame/{id_camara}"

    intervalo = 1.0 / FPS

    camara = None

    ultimo_error = 0

    print(
        f"[CAMARA {id_camara}] "
        f"Iniciando captura OpenCV {indice_opencv}"
    )

    try:

        while EJECUTANDO.is_set():

            # ----------------------------------------
            # ABRIR O RECONECTAR CÁMARA
            # ----------------------------------------

            if camara is None or not camara.isOpened():

                if camara is not None:
                    camara.release()

                print(
                    f"[CAMARA {id_camara}] "
                    "Intentando conectar..."
                )

                camara = cv2.VideoCapture(
                    indice_opencv,
                    cv2.CAP_DSHOW
                )

                if not camara.isOpened():

                    camara.release()
                    camara = None

                    print(
                        f"[CAMARA {id_camara}] "
                        "No disponible. Reintentando en 3 segundos."
                    )

                    EJECUTANDO.wait(3)
                    continue

                camara.set(
                    cv2.CAP_PROP_FRAME_WIDTH,
                    ANCHO
                )

                camara.set(
                    cv2.CAP_PROP_FRAME_HEIGHT,
                    ALTO
                )

                camara.set(
                    cv2.CAP_PROP_FPS,
                    FPS
                )

                print(
                    f"[CAMARA {id_camara}] Conectada "
                    f"| OpenCV índice {indice_opencv}"
                )

            inicio = time.time()

            # ----------------------------------------
            # LEER FOTOGRAMA
            # ----------------------------------------

            correcto, frame = camara.read()

            if not correcto or frame is None:

                print(
                    f"[CAMARA {id_camara}] "
                    "Error leyendo imagen. Reconectando..."
                )

                camara.release()
                camara = None

                EJECUTANDO.wait(1)
                continue

            # ----------------------------------------
            # CODIFICAR JPEG
            # ----------------------------------------

            correcto, buffer = cv2.imencode(
                ".jpg",
                frame,
                [
                    cv2.IMWRITE_JPEG_QUALITY,
                    CALIDAD_JPEG
                ]
            )

            if not correcto:
                continue

            # ----------------------------------------
            # ENVIAR A DOCKER
            # ----------------------------------------

            try:

                with sesion.post(
                    url,
                    data=buffer.tobytes(),
                    headers={
                        "Content-Type": "image/jpeg",
                        "X-Frame-Token": TOKEN_RECEPTOR
                    },
                    timeout=(2, 3)
                    
                ) as respuesta:

                    if respuesta.status_code != 200:

                        print(
                            f"[CAMARA {id_camara}] "
                            f"Respuesta HTTP: {respuesta.status_code} "
                            f"| Detalle: {respuesta.text[:300]}"
                        )
                    else:

                        print(
                            f"[CAMARA {id_camara}] "
                            "Fotograma enviado correctamente."
                        )

                        ultimo_error = 0

            except requests.RequestException as error:

                ahora = time.time()

                # Evitar imprimir el mismo error
                # continuamente.
                if ahora - ultimo_error >= 5:

                    print(
                        f"[CAMARA {id_camara}] "
                        f"Error de transmisión: {error}"
                    )

                    ultimo_error = ahora

                EJECUTANDO.wait(1)

            # ----------------------------------------
            # CONTROLAR FPS
            # ----------------------------------------

            transcurrido = time.time() - inicio

            espera = intervalo - transcurrido

            if espera > 0:
                EJECUTANDO.wait(espera)

    finally:

        if camara is not None:
            camara.release()

        sesion.close()

        print(
            f"[CAMARA {id_camara}] Captura finalizada."
        )


# ----------------------------------------------------
# PROGRAMA PRINCIPAL
# ----------------------------------------------------

def main():

    print("=" * 55)
    print("GERIAPP - CAPTURA DE CÁMARAS WINDOWS")
    print("=" * 55)

    print(
        f"Servidor receptor: {URL_RECEPTOR}"
    )

    if not TOKEN_RECEPTOR:
        print(
            "[ERROR] No está configurada la variable "
            "GERIAPP_FRAME_TOKEN."
        )
        return

    # ----------------------------------------
    # COMPROBAR RECEPTOR
    # ----------------------------------------

    try:

        respuesta = requests.get(
            f"{URL_RECEPTOR}/health",
            timeout=3
        )

        if respuesta.status_code != 200:

            print(
                "[ERROR] El receptor no está disponible."
            )

            return

        print(
            "[OK] Receptor Docker disponible."
        )

    except requests.RequestException:

        print(
            "[ERROR] No se puede conectar con Docker."
        )

        print(
            "Verifica que el contenedor esté iniciado."
        )

        return

    # ----------------------------------------
    # INICIAR HILOS
    # ----------------------------------------

    hilos = []

    try:

        for id_camara, indice_opencv in CAMARAS.items():

            hilo = threading.Thread(
                target=transmitir_camara,
                args=(id_camara, indice_opencv),
                name=f"Captura-Camara-{id_camara}",
                daemon=True
            )

            hilo.start()

            hilos.append(hilo)

        print("\nCaptura y transmisión iniciadas.")
        print("Presiona Ctrl+C para detener.\n")

        while EJECUTANDO.is_set():
            time.sleep(1)

    except KeyboardInterrupt:

        print("\nDeteniendo captura...")

    finally:

        EJECUTANDO.clear()

        for hilo in hilos:
            hilo.join(timeout=5)

        print(
            "Programa de captura detenido."
        )


if __name__ == "__main__":
    main()
