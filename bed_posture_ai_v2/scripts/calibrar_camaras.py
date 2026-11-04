import cv2
import yaml
import os

RUTA_CONFIG = "bed_posture_ai_v2/config/camaras.yaml"

# Cargar configuración
with open(RUTA_CONFIG, "r", encoding="utf-8") as archivo:
    config = yaml.safe_load(archivo)

puntos_seleccionados = []
imagen_original = None
nombre_ventana = "CALIBRACION DE CAMA"


def seleccionar_puntos(evento, x, y, flags, parametros):
    global puntos_seleccionados, imagen_original

    if evento == cv2.EVENT_LBUTTONDOWN:

        if len(puntos_seleccionados) < 4:
            puntos_seleccionados.append((x, y))
            print(f"Punto {len(puntos_seleccionados)}: ({x}, {y})")


def dibujar_puntos(imagen):
    resultado = imagen.copy()

    for i, punto in enumerate(puntos_seleccionados):
        cv2.circle(resultado, punto, 7, (0, 255, 0), -1)

        cv2.putText(
            resultado,
            str(i + 1),
            (punto[0] + 10, punto[1]),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

    if len(puntos_seleccionados) >= 2:
        for i in range(len(puntos_seleccionados) - 1):
            cv2.line(
                resultado,
                puntos_seleccionados[i],
                puntos_seleccionados[i + 1],
                (0, 255, 0),
                2
            )

    if len(puntos_seleccionados) == 4:
        cv2.line(
            resultado,
            puntos_seleccionados[3],
            puntos_seleccionados[0],
            (0, 255, 0),
            2
        )

    return resultado


# Calibrar cada cámara
for camara in config["camaras"]:

    nombre = camara["nombre"]
    indice = camara["indice"]

    print("\n================================")
    print(f"CALIBRANDO {nombre}")
    print("================================")

    captura = cv2.VideoCapture(indice, cv2.CAP_DSHOW)

    if not captura.isOpened():
        print(f"No se pudo abrir {nombre}")
        continue

    # Obtener imagen
    correcto, frame = captura.read()

    captura.release()

    if not correcto:
        print(f"No se pudo obtener imagen de {nombre}")
        continue

    puntos_seleccionados = []

    # Redimensionar para mostrar la imagen
    alto, ancho = frame.shape[:2]
    escala = min(1000 / ancho, 700 / alto, 1)

    nuevo_ancho = int(ancho * escala)
    nuevo_alto = int(alto * escala)

    imagen_original = cv2.resize(
        frame,
        (nuevo_ancho, nuevo_alto)
    )

    print("\nSelecciona las cuatro esquinas de la cama:")
    print("1. Superior izquierda")
    print("2. Superior derecha")
    print("3. Inferior derecha")
    print("4. Inferior izquierda")
    print("\nPresiona R para reiniciar.")
    print("Presiona ENTER para confirmar.")
    print("Presiona ESC para cancelar.")

    cv2.namedWindow(nombre_ventana)
    cv2.setMouseCallback(nombre_ventana, seleccionar_puntos)

    while True:

        imagen_mostrada = dibujar_puntos(imagen_original)

        cv2.imshow(nombre_ventana, imagen_mostrada)

        tecla = cv2.waitKey(20) & 0xFF

        if tecla == ord("r"):
            puntos_seleccionados = []
            print("Selección reiniciada.")

        elif tecla == 13:

            if len(puntos_seleccionados) == 4:

                # Convertir coordenadas a tamaño original
                puntos_originales = [
                    [
                        int(x / escala),
                        int(y / escala)
                    ]
                    for x, y in puntos_seleccionados
                ]

                camara["puntos_cama"] = puntos_originales

                print(f"\nCalibración guardada para {nombre}:")
                print(puntos_originales)

                break

            else:
                print("Debes seleccionar exactamente 4 puntos.")

        elif tecla == 27:
            print(f"Calibración cancelada para {nombre}.")
            break

    cv2.destroyAllWindows()


# Guardar configuración actualizada
with open(RUTA_CONFIG, "w", encoding="utf-8") as archivo:
    yaml.safe_dump(
        config,
        archivo,
        allow_unicode=True,
        sort_keys=False
    )

print("\n================================")
print("CALIBRACION FINALIZADA")
print("================================")
