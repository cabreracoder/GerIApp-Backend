
import os
import cv2
import json
from datetime import datetime

# ==========================================
# CONFIGURACIÓN
# ==========================================

CARPETA_ORIGINAL = "dataset_posturas/seleccionadas"

CARPETA_ENTRENAMIENTO = "entrenamiento_posturas"

POSTURAS = [
    "ACOSTADO",
    "SENTADO",
    "DE_PIE",
    "SIN_PERSONA"
]

CAMARAS = [
    "camara_1",
    "camara_2"
]

EXTENSIONES = (".jpg", ".jpeg", ".png")

# ==========================================
# VALIDAR IMÁGENES
# ==========================================

def revisar_imagen(ruta):
    imagen = cv2.imread(ruta)

    if imagen is None:
        return False, None

    alto, ancho = imagen.shape[:2]

    if alto == 0 or ancho == 0:
        return False, None

    return True, {
        "ancho": ancho,
        "alto": alto
    }


# ==========================================
# PREPARAR INFORME
# ==========================================

def preparar_dataset():

    informe = {
        "fecha_revision": datetime.now().isoformat(),
        "total_imagenes": 0,
        "imagenes_validas": 0,
        "imagenes_danadas": 0,
        "categorias": {}
    }

    print("\n======================================")
    print(" REVISION DEL DATASET DE GER IAPP")
    print("======================================\n")

    for postura in POSTURAS:

        informe["categorias"][postura] = {
            "total": 0,
            "validas": 0,
            "danadas": 0,
            "camaras": {}
        }

        print(f"\nPOSTURA: {postura}")

        for camara in CAMARAS:

            carpeta = os.path.join(
                CARPETA_ORIGINAL,
                postura,
                camara
            )

            total = 0
            validas = 0
            danadas = 0

            if not os.path.isdir(carpeta):
                print(f"  {camara}: carpeta no encontrada")
                continue

            for archivo in os.listdir(carpeta):

                if not archivo.lower().endswith(EXTENSIONES):
                    continue

                ruta = os.path.join(carpeta, archivo)

                total += 1

                correcta, dimensiones = revisar_imagen(ruta)

                if correcta:
                    validas += 1
                    informe["imagenes_validas"] += 1
                else:
                    danadas += 1
                    informe["imagenes_danadas"] += 1

                informe["total_imagenes"] += 1

            informe["categorias"][postura]["camaras"][camara] = {
                "total": total,
                "validas": validas,
                "danadas": danadas
            }

            informe["categorias"][postura]["total"] += total
            informe["categorias"][postura]["validas"] += validas
            informe["categorias"][postura]["danadas"] += danadas

            print(
                f"  {camara}: "
                f"{total} encontradas | "
                f"{validas} validas | "
                f"{danadas} danadas"
            )

    # ======================================
    # GUARDAR INFORME
    # ======================================

    carpeta_informes = os.path.join(
        CARPETA_ENTRENAMIENTO,
        "informes"
    )

    os.makedirs(carpeta_informes, exist_ok=True)

    ruta_informe = os.path.join(
        carpeta_informes,
        "informe_dataset.json"
    )

    with open(ruta_informe, "w", encoding="utf-8") as archivo:
        json.dump(
            informe,
            archivo,
            indent=4,
            ensure_ascii=False
        )

    print("\n======================================")
    print(" RESULTADO GENERAL")
    print("======================================")

    print(f"Total: {informe['total_imagenes']}")
    print(f"Validas: {informe['imagenes_validas']}")
    print(f"Danadas: {informe['imagenes_danadas']}")

    print(f"\nInforme guardado en: {ruta_informe}")


# ==========================================
# EJECUCIÓN
# ==========================================

if __name__ == "__main__":
    preparar_dataset()
