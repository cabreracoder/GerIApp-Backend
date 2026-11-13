
from pathlib import Path

import cv2
import numpy as np

from reconocimiento_facial.detector_rostros import DetectorRostros
from reconocimiento_facial.embeddings import GeneradorEmbeddings


class ReconocedorFacial:

    def __init__(self):

        self.detector = DetectorRostros()
        self.generador = GeneradorEmbeddings()

        print("Reconocedor facial inicializado.")

    def procesar_imagen(self, origen):

        # ==========================================
        # CARGAR IMAGEN DESDE RUTA O MEMORIA
        # ==========================================

        if isinstance(origen, (str, Path)):

            ruta = Path(origen)

            if not ruta.exists():
                raise FileNotFoundError(
                    f"No existe la imagen: {ruta}"
                )

            imagen = cv2.imread(str(ruta))

        else:

            if hasattr(origen, 'read'):

                if hasattr(origen, 'seek'):
                    origen.seek(0)

                contenido = origen.read()

            elif isinstance(origen, (bytes, bytearray)):
                contenido = origen

            else:
                raise TypeError(
                    "El formato de imagen recibido no es válido."
                )

            if not contenido:
                raise ValueError(
                    "La imagen recibida está vacía."
                )

            datos = np.frombuffer(
                contenido,
                dtype=np.uint8
            )

            imagen = cv2.imdecode(
                datos,
                cv2.IMREAD_COLOR
            )

        # ==========================================
        # VALIDAR IMAGEN
        # ==========================================

        if imagen is None:
            raise ValueError(
                "No fue posible leer la imagen."
            )

        # ==========================================
        # DETECTAR ROSTROS CON YUNET
        # ==========================================

        rostros = self.detector.detectar(imagen)

        print(f"Rostros detectados: {len(rostros)}")

        resultados = []

        # ==========================================
        # GENERAR EMBEDDINGS CON SFACE
        # ==========================================

        for indice, rostro in enumerate(rostros):

            embedding = self.generador.generar_embedding(
                imagen,
                rostro
            )

            resultados.append({
                "indice": indice,

                # Coordenadas del rostro detectado por YuNet
                "x": rostro["x"],
                "y": rostro["y"],
                "ancho": rostro["ancho"],
                "alto": rostro["alto"],

                # Puntos faciales
                "puntos_faciales": rostro["puntos_faciales"],

                # Confianza de detección
                "confianza_deteccion": rostro["confianza"],

                # Embedding generado por SFace
                "embedding": embedding
            })

            print(
                f"Rostro {indice + 1}: "
                "embedding generado correctamente."
            )

        return resultados

# ==========================================
# PRUEBA DEL RECONOCEDOR FACIAL
# ==========================================

if __name__ == "__main__":

    ruta = (
        Path(__file__).resolve().parent
        / "pruebas"
        / "rostro_prueba.jpg"
    )

    reconocedor = ReconocedorFacial()

    resultados = reconocedor.procesar_imagen(ruta)

    print("\nRESULTADO DE LA PRUEBA")

    for resultado in resultados:

        print(f"\nRostro {resultado['indice'] + 1}")

        print(
            "Coordenadas:",
            resultado["x"],
            resultado["y"],
            resultado["ancho"],
            resultado["alto"]
        )

        print(
            "Dimensiones del embedding:",
            resultado["embedding"].shape
        )

        print(
            "Confianza de detección:",
            round(resultado["confianza_deteccion"], 4)
        )

    if not resultados:
        print(
            "No se encontraron rostros en la fotografía."
        )
