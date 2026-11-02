import os
import shutil
import random

# Directorio base
BASE_DIR = "dataset_posturas"
DESTINO_DIR = os.path.join(BASE_DIR, "dataset_final_yolo")

# Mapeo para unificar todas las variantes a tus 4 clases principales
MAPEO_CLASES = {
    "ACOSTADO": "ACOSTADO",
    "ACOSTADO_CUBIERTO": "ACOSTADO",
    "ACOSTADO_DIFICIL": "ACOSTADO",
    
    "SENTADO": "SENTADO",
    "SENTADO_CUBIERTO": "SENTADO",
    "SENTADO_DIFICIL": "SENTADO",
    
    "DE_PIE": "DE_PIE",
    "DE_PIE_DIFICIL": "DE_PIE",
    
    "SIN_PERSONA": "SIN_PERSONA"
}

CLASES_FINALES = ["ACOSTADO", "SENTADO", "DE_PIE", "SIN_PERSONA"]
PORCENTAJE_TRAIN = 0.8

def unificar_y_preparar():
    if os.path.exists(DESTINO_DIR):
        shutil.rmtree(DESTINO_DIR)

    # Crear estructura train/val para cada clase final
    for split in ["train", "val"]:
        for clase in CLASES_FINALES:
            os.makedirs(os.path.join(DESTINO_DIR, split, clase), exist_ok=True)

    # Diccionario temporal para acumular todas las imágenes por clase final
    imagenes_por_clase = {clase: [] for clase in CLASES_FINALES}

    # 1. Recorrer 'seleccionadas' y 'nuevas_capturas'
    carpetas_origen = ["seleccionadas", "nuevas_capturas"]
    
    for carpeta in carpetas_origen:
        ruta_origen = os.path.join(BASE_DIR, carpeta)
        if not os.path.exists(ruta_origen):
            continue

        for subcarpeta_nombre in os.listdir(ruta_origen):
            ruta_sub = os.path.join(ruta_origen, subcarpeta_nombre)
            if not os.path.isdir(ruta_sub):
                continue

            # Buscar a qué clase final pertenece esta subcarpeta según el mapeo
            clase_destino = None
            for clave, valor in MAPEO_CLASES.items():
                if clave.lower() in subcarpeta_nombre.lower():
                    clase_destino = valor
                    break

            if not clase_destino:
                continue

            # Recorrer las subcarpetas internas (camara_1, camara_2, etc.)
            for cam_folder in os.listdir(ruta_sub):
                ruta_cam = os.path.join(ruta_sub, cam_folder)
                if os.path.isdir(ruta_cam):
                    # Extraer archivos de la cámara
                    for archivo in os.listdir(ruta_cam):
                        if archivo.lower().endswith(('.jpg', '.jpeg', '.png')):
                            ruta_img = os.path.join(ruta_cam, archivo)
                            # Prefijo único para evitar nombres repetidos entre cámaras/carpetas
                            nombre_unico = f"{carpeta}_{subcarpeta_nombre}_{cam_folder}_{archivo}"
                            imagenes_por_clase[clase_destino].append((ruta_img, nombre_unico))

    print("\n--- Resumen de recolección ---")
    total_general = 0
    
    # 2. Distribuir en train y val
    for clase, lista_imgs in imagenes_por_clase.items():
        random.shuffle(lista_imgs)
        corte = int(len(lista_imgs) * PORCENTAJE_TRAIN)
        train_imgs = lista_imgs[:corte]
        val_imgs = lista_imgs[corte:]

        print(f"Clase '{clase}': {len(train_imgs)} train, {len(val_imgs)} val (Total: {len(lista_imgs)})")
        total_general += len(lista_imgs)

        for ruta_img, nombre in train_imgs:
            shutil.copy(ruta_img, os.path.join(DESTINO_DIR, "train", clase, nombre))

        for ruta_img, nombre in val_imgs:
            shutil.copy(ruta_img, os.path.join(DESTINO_DIR, "val", clase, nombre))

    print(f"\n¡Listo! Dataset unificado y organizado en: {DESTINO_DIR} (Total imágenes: {total_general})")

if __name__ == "__main__":
    unificar_y_preparar()