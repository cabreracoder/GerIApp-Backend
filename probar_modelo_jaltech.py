
import cv2
from ultralytics import YOLO

# Modelo nuevo entrenado
RUTA_MODELO = "runs/classify/runs/classify/train-4/weights/best.pt"

# Índices de las dos cámaras Jaltech
CAMARA_1 = 1
CAMARA_2 = 2

def main():
    print("Cargando modelo YOLO train-4...")
    model = YOLO(RUTA_MODELO)

    print("Modelo cargado correctamente.")
    print("Clases:", model.names)

    # Abrir las dos cámaras
    cam1 = cv2.VideoCapture(CAMARA_1, cv2.CAP_DSHOW)
    cam2 = cv2.VideoCapture(CAMARA_2, cv2.CAP_DSHOW)

    if not cam1.isOpened():
        print("ERROR: No se pudo abrir la cámara 1.")
        return

    if not cam2.isOpened():
        print("ERROR: No se pudo abrir la cámara 2.")
        cam1.release()
        return

    print("Ambas cámaras están activas.")
    print("Presiona Q para salir.")

    try:
        while True:
            ret1, frame1 = cam1.read()
            ret2, frame2 = cam2.read()

            if not ret1 or not ret2:
                print("Error leyendo las cámaras.")
                break

            # Clasificar imagen de cada cámara
            result1 = model.predict(
                source=frame1,
                imgsz=640,
                verbose=False
            )[0]

            result2 = model.predict(
                source=frame2,
                imgsz=640,
                verbose=False
            )[0]

            # Obtener clase y confianza
            id1 = result1.probs.top1
            conf1 = float(result1.probs.top1conf)
            clase1 = model.names[id1]

            id2 = result2.probs.top1
            conf2 = float(result2.probs.top1conf)
            clase2 = model.names[id2]

            # Mostrar resultados
            cv2.putText(
                frame1,
                f"{clase1} - {conf1 * 100:.1f}%",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2
            )

            cv2.putText(
                frame2,
                f"{clase2} - {conf2 * 100:.1f}%",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2
            )

            cv2.imshow("GERIAPP - CAMARA JALTECH 1", frame1)
            cv2.imshow("GERIAPP - CAMARA JALTECH 2", frame2)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        cam1.release()
        cam2.release()
        cv2.destroyAllWindows()
        print("Prueba finalizada.")

if __name__ == "__main__":
    main()
