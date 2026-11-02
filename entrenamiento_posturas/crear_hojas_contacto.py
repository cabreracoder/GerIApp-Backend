
from pathlib import Path
from PIL import Image, ImageDraw
import math

BASE = Path(__file__).resolve().parent.parent
DATASET = BASE / "dataset_posturas" / "seleccionadas"
SALIDA = Path(__file__).resolve().parent / "resultados" / "hojas_contacto"

SALIDA.mkdir(parents=True, exist_ok=True)

EXTENSIONES = {".jpg", ".jpeg", ".png"}

def crear_hoja(camara):
    carpeta = DATASET / "ACOSTADO" / camara

    archivos = sorted(
        p for p in carpeta.iterdir()
        if p.suffix.lower() in EXTENSIONES
    )

    columnas = 3
    ancho_celda = 300
    alto_celda = 220
    filas = math.ceil(len(archivos) / columnas)

    hoja = Image.new(
        "RGB",
        (columnas * ancho_celda, filas * alto_celda),
        "white"
    )

    dibujo = ImageDraw.Draw(hoja)

    for indice, ruta in enumerate(archivos):
        with Image.open(ruta) as original:
            imagen = original.convert("RGB")
            imagen.thumbnail((280, 175))

        x = (indice % columnas) * ancho_celda
        y = (indice // columnas) * alto_celda

        hoja.paste(imagen, (x + 10, y + 5))

        dibujo.text(
            (x + 10, y + 183),
            f"{indice + 1}. {ruta.name}",
            fill="black"
        )

    destino = SALIDA / f"ACOSTADO_{camara}.jpg"
    hoja.save(destino, quality=90)

    print(f"{camara}: {len(archivos)} imágenes")
    print(f"Guardada: {destino}")

for camara in ["camara_1", "camara_2"]:
    crear_hoja(camara)

print("\nHojas de contacto creadas.")
