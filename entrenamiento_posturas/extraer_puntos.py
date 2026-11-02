
import os
import csv
import cv2
from ultralytics import YOLO

# ==========================================
# CONFIGURACION
# ==========================================
CARPETA_DATASET = "dataset_posturas/seleccionadas"
CARPETA_SALIDA = "entrenamiento_posturas/resultados"
MODELO = "yolo11n-pose.pt"

POSTURAS = ["ACOSTADO", "SENTADO", "DE_PIE"]
CAMARAS = ["camara_1", "camara_2"]
EXTENSIONES = (".jpg", ".jpeg", ".png")

# Confianza mínima para considerar útil un punto corporal.
CONFIANZA_MINIMA_PUNTO = 0.25

# ==========================================
# PROCESAMIENTO
# ==========================================
def main():
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    print("Cargando modelo YOLO Pose...")
    modelo = YOLO(MODELO)

    ruta_csv = os.path.join(
        CARPETA_SALIDA, "puntos_corporales.csv"
    )

    columnas = [
        "archivo", "postura", "camara",
        "personas_detectadas", "puntos_utiles",
        "estado_revision"
    ]

    # Agregar coordenadas y confianza para cada uno
    # de los 17 puntos corporales.
    for i in range(17):
        columnas.extend([
            f"x{i}", f"y{i}", f"confianza{i}"
        ])

    total = 0
    validas = 0
    revisar = 0
    sin_persona = 0

    with open(ruta_csv, "w", newline="", encoding="utf-8") as archivo_csv:
        escritor = csv.DictWriter(
            archivo_csv, fieldnames=columnas
        )
        escritor.writeheader()

        for postura in POSTURAS:
            for camara in CAMARAS:
                carpeta = os.path.join(
                    CARPETA_DATASET, postura, camara
                )

                if not os.path.isdir(carpeta):
                    print(f"Carpeta no encontrada: {carpeta}")
                    continue

                archivos = sorted([
                    nombre for nombre in os.listdir(carpeta)
                    if nombre.lower().endswith(EXTENSIONES)
                ])

                print(f"\n{postura} - {camara}: {len(archivos)} imágenes")

                for nombre in archivos:
                    ruta_imagen = os.path.join(carpeta, nombre)
                    imagen = cv2.imread(ruta_imagen)

                    if imagen is None:
                        print(f"Imagen ilegible: {ruta_imagen}")
                        continue

                    resultado = modelo.predict(
                        source=imagen,
                        conf=0.25,
                        imgsz=640,
                        verbose=False
                    )[0]

                    fila = {
                        "archivo": nombre,
                        "postura": postura,
                        "camara": camara,
                        "personas_detectadas": 0,
                        "puntos_utiles": 0,
                        "estado_revision": "REVISAR"
                    }

                    # Inicializar los 17 puntos como vacíos.
                    for i in range(17):
                        fila[f"x{i}"] = ""
                        fila[f"y{i}"] = ""
                        fila[f"confianza{i}"] = ""

                    personas = (
                        len(resultado.boxes)
                        if resultado.boxes is not None else 0
                    )
                    fila["personas_detectadas"] = personas

                    if (
                        personas == 0
                        or resultado.keypoints is None
                        or len(resultado.keypoints.data) == 0
                    ):
                        fila["estado_revision"] = "SIN_DETECCION"
                        sin_persona += 1
                        total += 1
                        escritor.writerow(fila)
                        continue

                    # Si hay varias detecciones, escoger la persona
                    # con la caja de mayor confianza.
                    indice = int(resultado.boxes.conf.argmax().item())
                    puntos_xy = resultado.keypoints.xy[indice].cpu().numpy()
                    puntos_conf = resultado.keypoints.conf[indice].cpu().numpy()

                    cantidad_utiles = 0

                    for i in range(min(17, len(puntos_xy))):
                        x, y = puntos_xy[i]
                        confianza = float(puntos_conf[i])

                        fila[f"confianza{i}"] = round(confianza, 4)

                        if confianza >= CONFIANZA_MINIMA_PUNTO:
                            fila[f"x{i}"] = round(float(x), 2)
                            fila[f"y{i}"] = round(float(y), 2)
                            cantidad_utiles += 1

                    fila["puntos_utiles"] = cantidad_utiles

                    # Umbral inicial de revisión, no una garantía
                    # de que la postura esté correctamente clasificada.
                    if cantidad_utiles >= 10:
                        fila["estado_revision"] = "VALIDA"
                        validas += 1
                    else:
                        fila["estado_revision"] = "REVISAR"
                        revisar += 1

                    escritor.writerow(fila)
                    total += 1

                    print(
                        f"{nombre} | puntos útiles: {cantidad_utiles}/17"
                        f" | {fila['estado_revision']}"
                    )

    print("\n======================================")
    print(" RESUMEN DE EXTRACCION")
    print("======================================")
    print(f"Imágenes procesadas: {total}")
    print(f"Con suficientes puntos: {validas}")
    print(f"Para revisar: {revisar}")
    print(f"Sin detección: {sin_persona}")
    print(f"\nCSV guardado en: {ruta_csv}")


if __name__ == "__main__":
    main()
