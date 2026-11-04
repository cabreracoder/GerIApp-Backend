import os
import shutil
from pathlib import Path
import random

# Ruta exacta que me indicaste
CARPETA_ORIGEN = Path("dataset posturas, fotos organizadas")
DESTINO_BASE = Path("./dataset_yolo_cls")
CLASES = ["acostado", "sentado", "de_pie"]

def preparar():
    if not CARPETA_ORIGEN.exists():
        print(f"[ERROR] No se encuentra la carpeta '{CARPETA_ORIGEN.absolute()}'. Verifica que esté en la raíz de tu proyecto.")
        return

    print(f"Leyendo imágenes desde: {CARPETA_ORIGEN.absolute()}")

    # Crear la estructura que exige YOLOv8-cls (train/ y val/ con subcarpetas por clase)
    for split in ["train", "val"]:
        for clase in CLASES:
            (DESTINO_BASE / split / clase).mkdir(parents=True, exist_ok=True)

    extensiones = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    total_procesadas = 0

    for clase in CLASES:
        # Buscar la subcarpeta de la clase (intentando variaciones por si acaso)
        sub_origen = None
        for posible_nombre in [clase, clase.capitalize(), clase.replace("_", " "), clase.replace("_", "")]:
            candidata = CARPETA_ORIGEN / posible_nombre
            if candidata.exists():
                sub_origen = candidata
                break
        
        if not sub_origen:
            print(f"[AVISO] No se encontró una subcarpeta para la clase '{clase}' dentro de '{CARPETA_ORIGEN}'. Revisa los nombres.")
            continue

        imagenes = [f for f in sub_origen.glob("*") if f.suffix.lower() in extensiones]
        
        if not imagenes:
            print(f"[AVISO] La carpeta '{sub_origen}' está vacía.")
            continue

        # Mezclar aleatoriamente
        random.shuffle(imagenes)
        split_idx = int(len(imagenes) * 0.8)  # 80% entrenamiento, 20% validación
        
        train_imgs = imagenes[:split_idx]
        val_imgs = imagenes[split_idx:]

        for img in train_imgs:
            shutil.copy2(img, DESTINO_BASE / "train" / clase / img.name)
        for img in val_imgs:
            shutil.copy2(img, DESTINO_BASE / "val" / clase / img.name)

        print(f" Clase '{clase}': {len(train_imgs)} train | {len(val_imgs)} val")
        total_procesadas += len(imagenes)

    print(f"\n ¡Dataset preparado con éxito en '{DESTINO_BASE.absolute()}'!")
    print(f"Total de imágenes distribuidas: {total_procesadas}")

if __name__ == "__main__":
    preparar()