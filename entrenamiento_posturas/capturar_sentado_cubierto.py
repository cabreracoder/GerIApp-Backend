
import cv2
import time
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent

SALIDA = (
    BASE / "dataset_posturas" / "nuevas_capturas"
    / "SENTADO_CUBIERTO"
)

CARPETAS = {
    1: SALIDA / "camara_1",
    2: SALIDA / "camara_2",
}

for carpeta in CARPETAS.values():
    carpeta.mkdir(parents=True, exist_ok=True)

camaras = {}

# Abrir las dos cámaras USB de GerIApp.
for indice in [1, 2]:
    captura = cv2.VideoCapture(indice, cv2.CAP_DSHOW)

    if not captura.isOpened():
        raise RuntimeError(f"No se pudo abrir la cámara {indice}")

    camaras[indice] = captura

INTERVALO = 3
contador = 0
captura_iniciada = False
ultima_captura = 0

print("\nCAPTURA AUTOMATICA: SENTADO CUBIERTO")
print("S: iniciar capturas")
print("Q: detener y salir")
print("Intervalo: cada 3 segundos")

try:
    while True:
        frames = {}

        for indice, captura in camaras.items():
            correcto, frame = captura.read()

            if correcto:
                frames[indice] = frame
                cv2.imshow(f"Camara {indice}", frame)

        if len(frames) != 2:
            print("Error: no se recibieron imágenes de ambas cámaras.")
            break

        tecla = cv2.waitKey(1) & 0xFF

        if tecla == ord("s") and not captura_iniciada:
            captura_iniciada = True
            ultima_captura = 0
            print("\n¡Capturas automáticas iniciadas!")

        if captura_iniciada:
            ahora = time.monotonic()

            if ahora - ultima_captura >= INTERVALO:
                momento = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                contador += 1

                for indice, frame in frames.items():
                    nombre = f"{momento}_{contador:04d}.jpg"
                    destino = CARPETAS[indice] / nombre

                    guardada = cv2.imwrite(str(destino), frame)

                    if not guardada:
                        print(f"Error al guardar cámara {indice}")

                ultima_captura = ahora
                print(f"Captura {contador} guardada en ambas cámaras.")

        if tecla == ord("q"):
            break

finally:
    for captura in camaras.values():
        captura.release()

    cv2.destroyAllWindows()

print(f"\nSesión finalizada. Total de capturas: {contador}")
print(f"Fotografías generadas: {contador * 2}")
