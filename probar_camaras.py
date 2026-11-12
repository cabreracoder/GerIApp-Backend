import cv2

for indice in [1, 2]:

    print(f"\nProbando cámara índice {indice}...")

    cap = cv2.VideoCapture(indice, cv2.CAP_DSHOW)

    if not cap.isOpened():
        print(f"No se pudo abrir la cámara {indice}")
        cap.release()
        continue

    print(f"Cámara {indice} abierta correctamente")

    while True:

        ret, frame = cap.read()

        if not ret:
            print("No se pudo obtener imagen")
            break

        cv2.imshow(f"Prueba cámara {indice}", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()