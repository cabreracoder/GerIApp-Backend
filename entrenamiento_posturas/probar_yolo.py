
import os
import cv2
from ultralytics import YOLO

# Modelo de detección de puntos corporales
modelo = YOLO("yolo11n-pose.pt")

# Una imagen de prueba por postura
imagenes = {
    "ACOSTADO": "dataset_posturas/seleccionadas/ACOSTADO/camara_1",
    "SENTADO": "dataset_posturas/seleccionadas/SENTADO/camara_1",
    "DE_PIE": "dataset_posturas/seleccionadas/DE_PIE/camara_1",
}

print("\n===== PRUEBA DE YOLO11 POSE =====\n")

for postura, carpeta in imagenes.items():

    archivos = sorted([
        f for f in os.listdir(carpeta)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])

    if not archivos:
        print(f"{postura}: no hay imágenes")
        continue

    ruta = os.path.join(carpeta, archivos[0])

    resultados = modelo.predict(
        source=ruta,
        conf=0.25,
        imgsz=640,
        verbose=False
    )

    resultado = resultados[0]

    personas = len(resultado.boxes) if resultado.boxes is not None else 0
    puntos = 0

    if resultado.keypoints is not None:
        puntos = len(resultado.keypoints.data[0])

    print(f"Postura: {postura}")
    print(f"Imagen: {archivos[0]}")
    print(f"Personas detectadas: {personas}")
    print(f"Puntos corporales: {puntos}")
    print("--------------------------------")
