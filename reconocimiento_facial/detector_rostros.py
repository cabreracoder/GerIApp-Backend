from pathlib import Path
import cv2


# Ruta del modelo YuNet
RUTA_MODELO = (
    Path(__file__).resolve().parent
    / "modelos"
    / "face_detection_yunet_2023mar.onnx"
)


class DetectorRostros:

    def __init__(self, confianza_minima=0.50, umbral_nms=0.30):

        if not RUTA_MODELO.exists():
            raise FileNotFoundError(
                f"No se encontró el modelo YuNet: {RUTA_MODELO}"
            )

        self.detector = None
        self.confianza_minima = confianza_minima
        self.umbral_nms = umbral_nms

        print("Detector YuNet inicializado correctamente.")

    def detectar(self, imagen):

        if imagen is None:
            raise ValueError("La imagen recibida está vacía.")

        if len(imagen.shape) != 3 or imagen.shape[2] != 3:
            raise ValueError(
                "La imagen debe tener tres canales BGR."
            )

        alto, ancho = imagen.shape[:2]

        # Inicializar el detector una sola vez
        if self.detector is None:

            self.detector = cv2.FaceDetectorYN.create(
                str(RUTA_MODELO),
                "",
                (ancho, alto),
                self.confianza_minima,
                self.umbral_nms,
                5000
            )

        else:

            self.detector.setInputSize((ancho, alto))

        # Detectar rostros
        _, resultados = self.detector.detect(imagen)

        rostros = []

        if resultados is None:
            return rostros

        for rostro in resultados:

            x, y, w, h = rostro[:4]

            puntos = rostro[4:14]

            confianza = float(rostro[14])

            rostros.append({
                "x": int(x),
                "y": int(y),
                "ancho": int(w),
                "alto": int(h),
                "puntos_faciales": puntos.tolist(),
                "confianza": confianza
            })

        return rostros