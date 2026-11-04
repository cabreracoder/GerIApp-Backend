from pathlib import Path
from ultralytics import YOLO
import cv2

# Rutas
RUTA_VIDEOS = Path("bed_posture_ai_v2/videos/SENTADO")
RUTA_SALIDA = Path("bed_posture_ai_v2/dataset_postura_de_pie/negativos")

# Configuración
MODELO = "yolo26n.pt"
CONFIANZA = 0.60
CADA_CUANTOS_FRAMES = 10
TAMANO_MINIMO = 80
MARGEN = 0.10

print("Cargando modelo YOLO...")
modelo = YOLO(MODELO)


def extraer_personas(camara):
    carpeta_videos = RUTA_VIDEOS / camara
    carpeta_salida = RUTA_SALIDA / camara

    carpeta_salida.mkdir(parents=True, exist_ok=True)

    videos = list(carpeta_videos.glob("*.mp4"))

    if not videos:
        print(f"No se encontraron videos en {carpeta_videos}")
        return

    total = 0

    for video in videos:
        print(f"\nProcesando: {video.name}")

        captura = cv2.VideoCapture(str(video))

        if not captura.isOpened():
            print("No se pudo abrir el video.")
            continue

        numero_frame = 0
        guardadas_video = 0

        while True:
            correcto, frame = captura.read()

            if not correcto:
                break

            numero_frame += 1

            if numero_frame % CADA_CUANTOS_FRAMES != 0:
                continue

            alto, ancho = frame.shape[:2]

            resultados = modelo.predict(
                frame,
                conf=CONFIANZA,
                classes=[0],
                verbose=False
            )

            for resultado in resultados:
                if resultado.boxes is None:
                    continue

                for caja in resultado.boxes.xyxy.cpu().numpy():
                    x1, y1, x2, y2 = map(int, caja)

                    ancho_persona = x2 - x1
                    alto_persona = y2 - y1

                    if ancho_persona < TAMANO_MINIMO:
                        continue

                    if alto_persona < TAMANO_MINIMO:
                        continue

                    margen_x = int(ancho_persona * MARGEN)
                    margen_y = int(alto_persona * MARGEN)

                    x1 = max(0, x1 - margen_x)
                    y1 = max(0, y1 - margen_y)
                    x2 = min(ancho, x2 + margen_x)
                    y2 = min(alto, y2 + margen_y)

                    recorte = frame[y1:y2, x1:x2]

                    if recorte.size == 0:
                        continue

                    nombre = (
                        f"SENTADO_{camara}_"
                        f"frame_{numero_frame:06d}_"
                        f"persona_{guardadas_video + 1}.jpg"
                    )

                    cv2.imwrite(
                        str(carpeta_salida / nombre),
                        recorte
                    )

                    guardadas_video += 1
                    total += 1

            if numero_frame % 500 == 0:
                print(f"Frames procesados: {numero_frame}")

        captura.release()

        print(f"Recortes obtenidos: {guardadas_video}")

    print(f"\nTotal de recortes de {camara}: {total}")


if __name__ == "__main__":
    extraer_personas("camara_1")
    extraer_personas("camara_2")

    print("\nExtracción finalizada.")
