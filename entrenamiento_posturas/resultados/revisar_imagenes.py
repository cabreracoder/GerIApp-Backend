
import csv
import shutil
from pathlib import Path

# Rutas del proyecto
BASE = Path(__file__).resolve().parent.parent.parent
CARPETA_DATASET = BASE / "dataset_posturas" / "seleccionadas"
ARCHIVO_CSV = Path(__file__).resolve().parent / "puntos_corporales.csv"

# Carpeta independiente para revisar las imágenes
CARPETA_REVISION = Path(__file__).resolve().parent / "imagenes_revision"
CARPETA_REVISION.mkdir(parents=True, exist_ok=True)

# Leer los registros que necesitan revisión
with open(ARCHIVO_CSV, "r", encoding="utf-8") as archivo:
    registros = csv.DictReader(archivo)

    for registro in registros:
        if registro["estado_revision"] == "VALIDA":
            continue

        postura = registro["postura"]
        camara = registro["camara"]
        nombre = registro["archivo"]

        # Buscar la imagen original
        origen = CARPETA_DATASET / postura / camara / nombre

        if not origen.exists():
            print(f"No encontrada: {origen}")
            continue

        # Crear una carpeta por postura y cámara
        destino_carpeta = CARPETA_REVISION / postura / camara
        destino_carpeta.mkdir(parents=True, exist_ok=True)

        # Copiar sin modificar la imagen original
        destino = destino_carpeta / nombre
        shutil.copy2(origen, destino)

        print(f"Copiada: {postura} | {camara} | {nombre}")

print("\nProceso terminado.")
print(f"Imágenes para revisar: {CARPETA_REVISION}")
