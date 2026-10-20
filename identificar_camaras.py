
import cv2

camaras = {
    "CAMARA OPEN CV 1": 1,
    "CAMARA OPEN CV 2": 2
}

abiertas = {}

try:
    for nombre, indice in camaras.items():
        camara = cv2.VideoCapture(indice, cv2.CAP_DSHOW)

        if camara.isOpened():
            camara.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            camara.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            abiertas[nombre] = camara
            print(f"{nombre}: conectada")
        else:
            print(f"{nombre}: no se pudo abrir")

    print("\nMira las dos ventanas.")
    print("Tapa físicamente una cámara y observa qué ventana se oscurece.")
    print("Presiona Q para terminar.")

    while True:
        for nombre, camara in abiertas.items():
            correcto, frame = camara.read()

            if correcto:
                cv2.putText(
                    frame,
                    nombre,
                    (15, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2
                )
                cv2.imshow(nombre, frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

finally:
    for camara in abiertas.values():
        camara.release()

    cv2.destroyAllWindows()
