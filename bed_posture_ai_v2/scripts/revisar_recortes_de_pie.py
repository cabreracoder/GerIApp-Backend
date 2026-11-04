import cv2
import math
import numpy as np
from pathlib import Path

RUTA_BASE = Path("bed_posture_ai_v2/dataset_postura_de_pie")

IMAGENES_POR_PAGINA = 25
COLUMNAS = 5
ANCHO_CELDA = 180
ALTO_CELDA = 230


def cargar_imagenes(carpeta):
    imagenes = sorted(carpeta.glob("*.jpg"))
    print(f"\nImágenes encontradas: {len(imagenes)}")
    return imagenes


def crear_pagina(imagenes, numero_pagina, titulo):
    filas = math.ceil(len(imagenes) / COLUMNAS)

    lienzo = np.ones(
        (filas * ALTO_CELDA, COLUMNAS * ANCHO_CELDA, 3),
        dtype=np.uint8
    ) * 255

    for i, ruta in enumerate(imagenes):
        imagen = cv2.imread(str(ruta))

        if imagen is None:
            continue

        alto, ancho = imagen.shape[:2]

        escala = min(
            (ANCHO_CELDA - 10) / ancho,
            (ALTO_CELDA - 45) / alto
        )

        nuevo_ancho = int(ancho * escala)
        nuevo_alto = int(alto * escala)

        imagen = cv2.resize(imagen, (nuevo_ancho, nuevo_alto))

        fila = i // COLUMNAS
        columna = i % COLUMNAS

        x = columna * ANCHO_CELDA
        y = fila * ALTO_CELDA

        lienzo[y:y + nuevo_alto, x:x + nuevo_ancho] = imagen

        nombre = ruta.name[:22]

        cv2.putText(
            lienzo,
            nombre,
            (x + 3, y + ALTO_CELDA - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (0, 0, 0),
            1
        )

    cv2.imshow(titulo, lienzo)


def revisar_carpeta(carpeta, titulo):
    imagenes = cargar_imagenes(carpeta)

    if not imagenes:
        print("No hay imágenes para revisar.")
        return

    total_paginas = math.ceil(len(imagenes) / IMAGENES_POR_PAGINA)
    pagina = 0

    while True:
        inicio = pagina * IMAGENES_POR_PAGINA
        fin = inicio + IMAGENES_POR_PAGINA

        crear_pagina(
            imagenes[inicio:fin],
            pagina + 1,
            titulo
        )

        print(f"\n{titulo} | Página {pagina + 1}/{total_paginas}")
        print("N = Siguiente página")
        print("A = Página anterior")
        print("Q = Terminar revisión")

        tecla = cv2.waitKey(0) & 0xFF

        if tecla == ord("n"):
            pagina = min(pagina + 1, total_paginas - 1)

        elif tecla == ord("a"):
            pagina = max(pagina - 1, 0)

        elif tecla == ord("q"):
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":

    print("\n1. Revisar DE_PIE")
    print("2. Revisar SENTADO")

    opcion = input("\nSelecciona una opción: ")

    if opcion == "1":
        revisar_carpeta(
            RUTA_BASE / "entrenamiento" / "camara_1",
            "Recortes DE_PIE - Camara 1"
        )

        revisar_carpeta(
            RUTA_BASE / "entrenamiento" / "camara_2",
            "Recortes DE_PIE - Camara 2"
        )

    elif opcion == "2":
        revisar_carpeta(
            RUTA_BASE / "negativos" / "camara_1",
            "Recortes SENTADO - Camara 1"
        )

        revisar_carpeta(
            RUTA_BASE / "negativos" / "camara_2",
            "Recortes SENTADO - Camara 2"
        )

    else:
        print("Opción no válida.")