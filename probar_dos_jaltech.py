import cv2

for indice in range(5):

    camara = cv2.VideoCapture(indice, cv2.CAP_DSHOW)

    if camara.isOpened():

        correcto, frame = camara.read()

        if correcto:
            print(f"Índice {indice}: Cámara disponible")

        else:
            print(f"Índice {indice}: No entrega imagen")

        camara.release()

    else:
        print(f"Índice {indice}: No disponible")