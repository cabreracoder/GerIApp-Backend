import cv2
from ultralytics import YOLO
from pathlib import Path

# Rutas
RUTA_VIDEOS = Path("bed_posture_ai_v2/videos/DE_PIE")
RUTA_DATASET = Path("bed_posture_ai_v2/dataset_postura_de_pie/entrenamiento")

# Configuración
CONFIANZA = 0.60
TAMANO_MINIMO = 80

# Cargar modelo YOLO preentrenado
modelo = YOLO("yolo26n.pt")

def extraer_personas(ruta_video, nombre_camara):

    cap = cv2.VideoCapture(str(ruta_video))

    if not cap.isOpened():
        print(f"No se pudo abrir: {ruta_video}")
        return

    contador = 0
    frame_numero = 0

    carpeta_salida = RUTA_DATASET / nombre_camara
    carpeta_salida.mkdir(parents=True, exist_ok=True)

    print(f"\nProcesando: {ruta_video}")

    while True:
        ret, frame = cap.read()

        if not ret:
            break

        frame_numero += 1

        # Procesar un frame cada 10
        if frame_numero % 10 != 0:
            continue

        resultados = modelo.predict(
            frame,
            conf=CONFIANZA,
            classes=[0],
            verbose=False
        )

        for resultado in resultados:

            for caja in resultado.boxes:

                x1, y1, x2, y2 = map(int, caja.xyxy[0].tolist())

                ancho = x2 - x1
                alto = y2 - y1

                if ancho < TAMANO_MINIMO or alto < TAMANO_MINIMO:
                    continue

                # Agregar margen del 10 %
                margen_x = int(ancho * 0.10)
                margen_y = int(alto * 0.10)

                x1 = max(0, x1 - margen_x)
                y1 = max(0, y1 - margen_y)
                x2 = min(frame.shape[1], x2 + margen_x)
                y2 = min(frame.shape[0], y2 + margen_y)

                recorte = frame[y1:y2, x1:x2]

                if recorte.size == 0:
                    continue

                contador += 1

                nombre = (
                    f"{ruta_video.stem}_"
                    f"frame_{frame_numero}_"
                    f"persona_{contador}.jpg"
                )

                cv2.imwrite(str(carpeta_salida / nombre), recorte)

        if frame_numero % 200 == 0:
            print(f"Frames procesados: {frame_numero}")

    cap.release()

    print(f"Recortes guardados: {contador}")


def main():

    for camara in ["camara_1", "camara_2"]:

        carpeta = RUTA_VIDEOS / camara

        if not carpeta.exists():
            print(f"No existe: {carpeta}")
            continue

        videos = list(carpeta.glob("*.mp4"))

        for video in videos:
            extraer_personas(video, camara)

    print("\nExtracción finalizada.")


if __name__ == "__main__":
    main()
