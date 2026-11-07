from pathlib import Path

import cv2

from reconocimiento_facial.detector_rostros import DetectorRostros
from reconocimiento_facial.embeddings import GeneradorEmbeddings


class ReconocedorFacial:

    def __init__(self):

        self.detector = DetectorRostros()
        self.generador = GeneradorEmbeddings()

        print("Reconocedor facial inicializado.")

    def procesar_imagen(self, ruta_imagen):

        ruta = Path(ruta_imagen)

        if not ruta.exists():
            raise FileNotFoundError(
                f"No existe la imagen: {ruta}"
            )

        imagen = cv2.imread(str(ruta))

        if imagen is None:
            raise ValueError(
                "No fue posible leer la imagen."
            )

        rostros = self.detector.detectar(imagen)

        print(f"Rostros detectados: {len(rostros)}")

        resultados = []

        for indice, rostro in enumerate(rostros):

            embedding = self.generador.generar_embedding(
                imagen,
                rostro
            )

            resultados.append({
                "indice": indice,
                "confianza_deteccion": rostro["confianza"],
                "embedding": embedding
            })

            print(
                f"Rostro {indice + 1}: "
                f"embedding generado correctamente."
            )

        return resultados


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

        print(
            "Dimensiones del embedding:",
            resultado["embedding"].shape
        )

        print(
            "Confianza de detección:",
            round(resultado["confianza_deteccion"], 4)
        )

    if not resultados:
        print("No se encontraron rostros en la fotografía.")