import os
import cv2

# Ruta donde tienes guardadas tus imágenes clasificadas
CARPETA_DATASET = os.path.join("dataset_posturas", "seleccionadas")

def limpiar_dataset():
    if not os.path.exists(CARPETA_DATASET):
        print(f"No se encontró la carpeta: {CARPETA_DATASET}")
        return

    # Recorrer todas las categorías y subcarpetas de cámaras
    for categoria in os.listdir(CARPETA_DATASET):
        ruta_categoria = os.path.join(CARPETA_DATASET, categoria)
        
        if not os.path.isdir(ruta_categoria):
            continue

        print(f"\n--- Revisando categoría: {categoria} ---")
        
        # Buscar en las subcarpetas (ej. camara_1, camara_2)
        for subfolder in os.listdir(ruta_categoria):
            ruta_sub = os.path.join(ruta_categoria, subfolder)
            
            if not os.path.isdir(ruta_sub):
                continue

            imagenes = [f for f in os.listdir(ruta_sub) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            
            if not imagenes:
                continue

            print(f"Subcarpeta: {subfolder} ({len(imagenes)} imágenes)")
            print("Controles: [ESPACIO o ENTER] = Conservar | [D o SUPR] = Borrar imagen | [ESC] = Salir")

            for img_nombre in imagenes:
                ruta_imagen = os.path.join(ruta_sub, img_nombre)
                frame = cv2.imread(ruta_imagen)

                if frame is None:
                    continue

                # Mostrar el nombre del archivo y la categoría en la imagen
                display_frame = frame.copy()
                cv2.putText(display_frame, f"Cat: {categoria}", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(display_frame, "[ESPACIO]=Guardar  [D]=Borrar", (10, 60), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                cv2.imshow("Limpieza de Dataset - GerIApp", display_frame)
                tecla = cv2.waitKey(0) & 0xFF

                # Tecla ESC para salir por completo
                if tecla == 27:
                    print("\nProceso de limpieza interrumpido por el usuario.")
                    cv2.destroyAllWindows()
                    return

                # Tecla 'd' o retroceso para borrar
                elif tecla in (ord('d'), ord('D'), 8):
                    os.remove(ruta_imagen)
                    print(f"[BORRADA] {img_nombre}")

                # Cualquier otra tecla (como espacio o enter) conserva la imagen
                else:
                    print(f"[CONSERVADA] {img_nombre}")

    cv2.destroyAllWindows()
    print("\n¡Limpieza de dataset finalizada con éxito!")

if __name__ == "__main__":
    limpiar_dataset()