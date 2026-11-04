import cv2
import yaml
import os
import time
from datetime import datetime

RUTA_CONFIG = "bed_posture_ai_v2/config/camaras.yaml"
RUTA_VIDEOS = "bed_posture_ai_v2/videos"

DURACION_GRABACION = 300
TIEMPO_PREPARACION = 3


def cargar_configuracion():
    with open(RUTA_CONFIG, "r", encoding="utf-8") as archivo:
        return yaml.safe_load(archivo)


def seleccionar_postura():

    print("\n========== GRABACIÓN DE VIDEOS ==========")
    print("1. ACOSTADO")
    print("2. SENTADO")
    print("3. SIN_PERSONA")
    print("4. DE_PIE")

    clases = {
        "1": "ACOSTADO",
        "2": "SENTADO",
        "3": "SIN_PERSONA",
        "4": "DE_PIE"
    }

    opcion = input("\nSelecciona la postura: ").strip()

    if opcion not in clases:
        raise ValueError("Opción no válida.")

    return clases[opcion]


def conectar_camaras(config):

    camaras = []

    print("\nConectando cámaras...")

    for camara in config["camaras"]:

        nombre = camara["nombre"]
        indice = camara["indice"]

        captura = cv2.VideoCapture(indice, cv2.CAP_DSHOW)

        if not captura.isOpened():
            captura.release()
            raise RuntimeError(f"No se pudo abrir {nombre}")

        correcto, frame = captura.read()

        if not correcto:
            captura.release()
            raise RuntimeError(f"No se pudo leer {nombre}")

        alto, ancho = frame.shape[:2]

        camaras.append({
            "nombre": nombre,
            "captura": captura,
            "ancho": ancho,
            "alto": alto,
            "writer": None,
            "ruta_video": None
        })

        print(f"[OK] {nombre} conectada")

    if len(camaras) != 2:
        raise RuntimeError("Se necesitan exactamente dos cámaras.")

    return camaras


def preparar_videos(camaras, postura, config):

    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")

    fps = config["captura"]["fps"]

    for camara in camaras:

        carpeta = os.path.join(
            RUTA_VIDEOS,
            postura,
            camara["nombre"]
        )

        os.makedirs(carpeta, exist_ok=True)

        nombre_video = (
            f"{postura}_{camara['nombre']}_{fecha}.mp4"
        )

        ruta_video = os.path.join(carpeta, nombre_video)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")

        writer = cv2.VideoWriter(
            ruta_video,
            fourcc,
            fps,
            (camara["ancho"], camara["alto"])
        )

        if not writer.isOpened():
            writer.release()
            raise RuntimeError(f"No se pudo crear {ruta_video}")

        camara["writer"] = writer
        camara["ruta_video"] = ruta_video

        print(f"[PREPARADO] {ruta_video}")


def cuenta_regresiva(camaras):

    print("\nLa grabación comienza en 3 segundos.")

    inicio = time.monotonic()

    while time.monotonic() - inicio < TIEMPO_PREPARACION:

        restante = max(
            1,
            TIEMPO_PREPARACION - int(time.monotonic() - inicio)
        )

        for camara in camaras:

            correcto, frame = camara["captura"].read()

            if not correcto:
                raise RuntimeError(
                    f"No se pudo leer {camara['nombre']}"
                )

            cv2.putText(
                frame,
                f"INICIANDO EN: {restante}",
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 255),
                2
            )

            cv2.imshow(camara["nombre"], frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            raise KeyboardInterrupt("Grabación cancelada.")


def grabar(camaras, postura):

    tiempo_grabado = 0
    ultimo_tiempo = time.monotonic()

    pausado = False
    finalizar = False

    print("\n[GRABANDO]")
    print("P = Pausar")
    print("R = Reanudar")
    print("S = Guardar y finalizar")
    print("Q = Finalizar y salir")

    while not finalizar:

        ahora = time.monotonic()

        if not pausado:
            tiempo_grabado += ahora - ultimo_tiempo

        ultimo_tiempo = ahora

        if tiempo_grabado >= DURACION_GRABACION:
            print("\n[FINALIZADO] Se cumplieron los 5 minutos.")
            break

        restante = max(
            0,
            int(DURACION_GRABACION - tiempo_grabado)
        )

        minutos = restante // 60
        segundos = restante % 60

        for camara in camaras:

            correcto, frame = camara["captura"].read()

            if not correcto:
                raise RuntimeError(
                    f"Se perdió la conexión con {camara['nombre']}"
                )

            if not pausado:

                camara["writer"].write(frame)

                estado = "GRABANDO"
                color = (0, 0, 255)

            else:

                estado = "PAUSADO"
                color = (0, 255, 255)

            cv2.putText(
                frame,
                f"{estado} - {postura}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2
            )

            cv2.putText(
                frame,
                f"TIEMPO: {minutos:02d}:{segundos:02d}",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2
            )

            cv2.imshow(camara["nombre"], frame)

        tecla = cv2.waitKey(1) & 0xFF

        if tecla == ord("p") and not pausado:

            pausado = True
            print("\n[PAUSADO] Puedes cambiar de posición.")

        elif tecla == ord("r") and pausado:

            pausado = False
            ultimo_tiempo = time.monotonic()

            print("\n[REANUDADO] Continuando grabación.")

        elif tecla == ord("s"):

            print("\n[FINALIZADO] Guardando videos.")
            finalizar = True

        elif tecla == ord("q"):

            print("\n[FINALIZADO] Guardando videos.")
            finalizar = True


def main():

    camaras = []

    try:

        config = cargar_configuracion()

        postura = seleccionar_postura()

        camaras = conectar_camaras(config)

        preparar_videos(camaras, postura, config)

        cuenta_regresiva(camaras)

        grabar(camaras, postura)

    except KeyboardInterrupt:

        print("\n[AVISO] Grabación interrumpida.")

    except Exception as error:

        print(f"\n[ERROR] {error}")

    finally:

        for camara in camaras:

            if camara["writer"] is not None:
                camara["writer"].release()

            camara["captura"].release()

        cv2.destroyAllWindows()

        print("\n================================")
        print("GRABACIÓN FINALIZADA")
        print("================================")


if __name__ == "__main__":
    main()