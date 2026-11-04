import os
import cv2
import numpy as np

# Rutas de origen y destino
CARPETA_ORIGEN = "dataset_posturas/fotos_organizadas"
CARPETA_DESTINO = "dataset_geriap"
CLASES = [ "DE_PIE", "SIN_PERSONA"]

# Variables globales para los 4 puntos
puntos = []
img_copia = None

def click_cuatro_puntos(event, x, y, flags, param):
    global puntos, img_copia
    
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(puntos) < 4:
            puntos.append((x, y))
            # Dibujar un círculo pequeño en cada punto seleccionado
            cv2.circle(img_copia, (x, y), 5, (0, 0, 255), -1)
            
            # Si ya tenemos los 4 puntos, dibujamos el rectángulo completo
            if len(puntos) == 4:
                pts = np.array(puntos, dtype=np.int32)
                # Encontrar los límites mínimos y máximos para formar el rectángulo alineado
                x_coords = [p[0] for p in puntos]
                y_coords = [p[1] for p in puntos]
                x1, x2 = min(x_coords), max(x_coords)
                y1, y2 = min(y_coords), max(y_coords)
                
                # Dibujar el rectángulo verde resultante
                cv2.rectangle(img_copia, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
            cv2.imshow("Recorte por 4 Clics - [ENTER: Guardar] [R: Reiniciar] [ESC: Omitir]", img_copia)

def iniciar_recorte_manual():
    global puntos, img_copia
    
    print("🚀 Iniciando herramienta de recorte por 4 Clics...")
    print("INSTRUCCIONES:")
    print("1. Haz clic en las **4 esquinas** de la cama (en cualquier orden).")
    print("2. Presiona [ENTER] o [ESPACIO] para confirmar el recorte automático.")
    print("3. Presiona [R] si te equivocas y quieres volver a hacer los 4 clics en esta foto.")
    print("4. Presiona [ESC] para saltar la foto actual.\n")
    
    # Crear estructura de carpetas destino
    for fase in ["train", "val"]:
        for clase in CLASES:
            os.makedirs(os.path.join(CARPETA_DESTINO, fase, clase), exist_ok=True)
            
    win_name = "Recorte por 4 Clics - [ENTER: Guardar] [R: Reiniciar] [ESC: Omitir]"
    cv2.namedWindow(win_name)
    cv2.setMouseCallback(win_name, click_cuatro_puntos, None)
    
    total_procesadas = 0

    for clase in CLASES:
        dir_clase_origen = os.path.join(CARPETA_ORIGEN, clase)
        if not os.path.exists(dir_clase_origen):
            continue
            
        archivos_con_ruta = []
        for root, _, files in os.walk(dir_clase_origen):
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                    archivos_con_ruta.append(os.path.join(root, file))
                    
        print(f"\n📂 Procesando clase '{clase}' ({len(archivos_con_ruta)} imágenes)...")
        
        for i, ruta_imagen in enumerate(archivos_con_ruta):
            img = cv2.imread(ruta_imagen)
            if img is None:
                continue
                
            img_copia = img.copy()
            puntos = []
            
            while True:
                cv2.imshow(win_name, img_copia)
                key = cv2.waitKey(1) & 0xFF
                
                # Enter o Espacio para guardar
                if key == 13 or key == 32: 
                    if len(puntos) == 4:
                        x_coords = [p[0] for p in puntos]
                        y_coords = [p[1] for p in puntos]
                        x1, x2 = max(0, min(x_coords)), min(img.shape[1], max(x_coords))
                        y1, y2 = max(0, min(y_coords)), min(img.shape[0], max(y_coords))
                        
                        recorte = img[y1:y2, x1:x2]
                        if recorte.size > 0:
                            recorte_resized = cv2.resize(recorte, (224, 224))
                            
                            # Asignar 80% train / 20% val
                            fase_destino = "val" if i < (len(archivos_con_ruta) * 0.20) else "train"
                            nombre_archivo = f"manual4p_{i}_{os.path.basename(ruta_imagen)}"
                            ruta_salida = os.path.join(CARPETA_DESTINO, fase_destino, clase, nombre_archivo)
                            
                            cv2.imwrite(ruta_salida, recorte_resized)
                            total_procesadas += 1
                            break
                    else:
                        print("  [!] Debes hacer exactamente 4 clics antes de guardar.")
                    
                # Tecla 'r' para reiniciar los puntos de esta foto
                elif key == ord('r') or key == ord('R'):
                    img_copia = img.copy()
                    puntos = []
                    cv2.imshow(win_name, img_copia)
                    
                # Tecla ESC para saltar la foto
                elif key == 27:
                    break

    cv2.destroyAllWindows()
    print("\n--------------------------------------------------")
    print(f"¡Proceso por 4 clics finalizado! Se guardaron {total_procesadas} recortes perfectos.")
    print(f"Dataset organizado en: '{CARPETA_DESTINO}'")
    print("--------------------------------------------------")

if __name__ == "__main__":
    iniciar_recorte_manual()