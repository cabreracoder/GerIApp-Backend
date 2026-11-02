import csv
from pathlib import Path

BASE = Path(__file__).resolve().parent
ARCHIVO_CSV = BASE / "resultados" / "inventario_clasificador.csv"

with open(ARCHIVO_CSV, "r", newline="", encoding="utf-8-sig") as archivo:
    lector = csv.DictReader(archivo)
    columnas = lector.fieldnames
    filas = list(lector)

for camara in ["camara_1", "camara_2"]:
    imagenes = [
        fila for fila in filas
        if fila["postura_carpeta"] == "ACOSTADO"
        and fila["camara"] == camara
    ]

    imagenes.sort(key=lambda fila: fila["archivo"])

    for indice, fila in enumerate(imagenes, start=1):
        if indice <= 17:
            fila["tipo_acostado"] = "ACOSTADO_VISIBLE"
        else:
            fila["tipo_acostado"] = "ACOSTADO_CUBIERTO"

with open(ARCHIVO_CSV, "w", newline="", encoding="utf-8-sig") as archivo:
    escritor = csv.DictWriter(archivo, fieldnames=columnas)
    escritor.writeheader()
    escritor.writerows(filas)

print("Clasificación registrada correctamente.")

for camara in ["camara_1", "camara_2"]:
    visibles = sum(
        1 for fila in filas
        if fila["camara"] == camara
        and fila["tipo_acostado"] == "ACOSTADO_VISIBLE"
    )
    cubiertas = sum(
        1 for fila in filas
        if fila["camara"] == camara
        and fila["tipo_acostado"] == "ACOSTADO_CUBIERTO"
    )

    print(f"{camara}: {visibles} visibles, {cubiertas} cubiertas")