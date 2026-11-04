
from pathlib import Path
import random
import shutil
import math

ORIGEN = Path("dataset_posturas/fotos_organizadas")
DESTINO = Path("dataset_posturas/dataset_final_yolo_v2")

CLASES = ["ACOSTADO", "SENTADO", "DE_PIE", "SIN_PERSONA"]
CAMARAS = ["camara_1", "camara_2"]

EXTENSIONES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

PORCENTAJE_TRAIN = 0.70
SEMILLA = 42


def preparar_dataset():
    random.seed(SEMILLA)

    if not ORIGEN.exists():
        print(f"[ERROR] No existe: {ORIGEN}")
        return

    if DESTINO.exists():
        print(f"[ERROR] Ya existe el destino: {DESTINO}")
        print("No se modificó para evitar sobrescribir imágenes.")
        return

    total_general = 0

    for clase in CLASES:

        imagenes = []

        # Buscar dentro de las dos cámaras
        for camara in CAMARAS:

            carpeta = ORIGEN / clase / camara

            if not carpeta.exists():
                print(f"[AVISO] No existe: {carpeta}")
                continue

            archivos = [
                p for p in carpeta.iterdir()
                if p.is_file() and p.suffix.lower() in EXTENSIONES
            ]

            for imagen in archivos:
                imagenes.append((camara, imagen))

        if not imagenes:
            print(f"[ERROR] No hay imágenes en {clase}")
            continue

        random.shuffle(imagenes)

        cantidad_train = math.floor(
            len(imagenes) * PORCENTAJE_TRAIN
        )

        entrenamiento = imagenes[:cantidad_train]
        validacion = imagenes[cantidad_train:]

        for conjunto, lista in [
            ("train", entrenamiento),
            ("val", validacion)
        ]:

            carpeta_destino = DESTINO / conjunto / clase
            carpeta_destino.mkdir(parents=True, exist_ok=True)

            for camara, imagen in lista:

                # Identificar la cámara para evitar nombres repetidos
                nombre = f"{camara}_{imagen.name}"

                shutil.copy2(
                    imagen,
                    carpeta_destino / nombre
                )

        total_general += len(imagenes)

        print(f"\n{clase}")
        print(f"  Total: {len(imagenes)}")
        print(f"  Train: {len(entrenamiento)}")
        print(f"  Val: {len(validacion)}")

    print("\n================================")
    print("DATASET PREPARADO")
    print("================================")
    print(f"Total de imágenes: {total_general}")
    print(f"Destino: {DESTINO}")


if __name__ == "__main__":
    preparar_dataset()
