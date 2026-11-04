
import cv2

# Abrimos únicamente las dos cámaras JALTECH.
camara_1 = cv2.VideoCapture(1, cv2.CAP_DSHOW)
camara_2 = cv2.VideoCapture(2, cv2.CAP_DSHOW)

camaras = {
    "JALTECH 1": camara_1,
    "JALTECH 2": camara_2,
}

try:
    for nombre, camara in camaras.items():
        if not camara.isOpened():
            raise RuntimeError(f"No se pudo abrir {nombre}")

        camara.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camara.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        print(f"{nombre}: abierta correctamente")

    print("Las dos cámaras están funcionando. Presiona Q para salir.")

    while True:
        for nombre, camara in camaras.items():
            correcto, imagen = camara.read()

            if correcto:
                cv2.imshow(nombre, imagen)
            else:
                print(f"No se recibió imagen de {nombre}")

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

finally:
    camara_1.release()
    camara_2.release()
    cv2.destroyAllWindows()
    print("Prueba finalizada.")
