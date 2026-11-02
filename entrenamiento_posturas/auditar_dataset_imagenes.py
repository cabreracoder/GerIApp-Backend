
import csv
import hashlib
from pathlib import Path
from PIL import Image

# Rutas del proyecto
BASE = Path(__file__).resolve().parent.parent
DATASET = BASE / "dataset_posturas" / "seleccionadas"
RESULTADOS = Path(__file__).resolve().parent / "resultados"

RESULTADOS.mkdir(parents=True, exist_ok=True)

ARCHIVO_SALIDA = RESULTADOS / "inventario_clasificador.csv"

EXTENSIONES = {".jpg", ".jpeg", ".png", ".bmp"}

posturas = [
    "ACOSTADO",
    "SENTADO",
    "DE_PIE",
    "SIN_PERSONA"
]

inventario = []
huellas = {}

for postura in posturas:
    for camara in ["camara_1", "camara_2"]:

        carpeta = DATASET / postura / camara

        if not carpeta.exists():
            print(f"Carpeta no encontrada: {carpeta}")
            continue

        for imagen in sorted(carpeta.iterdir()):

            if imagen.suffix.lower() not in EXTENSIONES:
                continue

            try:
                # Leer dimensiones sin modificar la imagen
                with Image.open(imagen) as img:
                    ancho, alto = img.size
                    img.verify()

                # Calcular huella para identificar duplicados exactos
                huella = hashlib.sha256(imagen.read_bytes()).hexdigest()

                duplicada = huella in huellas

                if not duplicada:
                    huellas[huella] = str(imagen)

                inventario.append({
                    "archivo": imagen.name,
                    "ruta": str(imagen),
                    "postura_carpeta": postura,
                    "camara": camara,
                    "ancho": ancho,
                    "alto": alto,
                    "duplicada_exacta": duplicada,
                    "tipo_acostado": (
                        "PENDIENTE" if postura == "ACOSTADO" else ""
                    ),
                    "observacion_manual": ""
                })

            except Exception as error:
                print(f"Error leyendo {imagen.name}: {error}")

# Guardar inventario
with open(ARCHIVO_SALIDA, "w", newline="", encoding="utf-8-sig") as archivo:
    campos = [
        "archivo",
        "ruta",
        "postura_carpeta",
        "camara",
        "ancho",
        "alto",
        "duplicada_exacta",
        "tipo_acostado",
        "observacion_manual"
    ]

    escritor = csv.DictWriter(archivo, fieldnames=campos)
    escritor.writeheader()
    escritor.writerows(inventario)

# Mostrar resumen
print("\nRESUMEN DEL DATASET")

for postura in posturas:
    cantidad = sum(
        1 for registro in inventario
        if registro["postura_carpeta"] == postura
    )
    print(f"{postura}: {cantidad}")

print(f"\nTotal de imágenes: {len(inventario)}")
print(f"Duplicados exactos: {sum(x['duplicada_exacta'] for x in inventario)}")
print(f"\nInventario guardado en: {ARCHIVO_SALIDA}")

