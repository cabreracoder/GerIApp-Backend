import cv2
import yaml

# Cargar configuración
with open("bed_posture_ai_v2/config/camaras.yaml", "r", encoding="utf-8") as archivo:
    config = yaml.safe_load(archivo)

camaras = []

# Abrir las dos cámaras
for camara in config["camaras"]:
    indice = camara["indice"]
    nombre = camara["nombre"]

    captura = cv2.VideoCapture(indice, cv2.CAP_DSHOW)

    if not captura.isOpened():
        print(f"[ERROR] No se pudo abrir {nombre} (índice {indice})")
        continue

    captura.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    captura.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    camaras.append((nombre, captura))
    print(f"[OK] {nombre} conectada correctamente")

if not camaras:
    print("No se pudo conectar ninguna cámara.")
    exit()

print("\nPresiona Q para cerrar las cámaras.")

while True:
    for nombre, captura in camaras:
        correcto, frame = captura.read()

        if correcto:
            cv2.imshow(nombre, frame)
        else:
            print(f"[ERROR] No se pudo leer imagen de {nombre}")

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

# Liberar cámaras
for nombre, captura in camaras:
    captura.release()

cv2.destroyAllWindows()
