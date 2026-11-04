from ultralytics import YOLO

def entrenar():
    print("🚀 Cargando modelo base YOLOv11 nano para clasificación...")
    # Cargamos el modelo pre-entrenado de clasificación más ligero de YOLOv11
    model = YOLO("yolo11n-cls.pt")
    
    print("🏋️‍♂️ Iniciando entrenamiento con el dataset curado de GerIApp...")
    # Entrenamos usando tu dataset estructurado por clases
    results = model.train(
        data="dataset_geriap",  # Carpeta con train/ y val/
        epochs=30,              # Número de épocas de entrenamiento
        imgsz=224,              # Tamaño estándar de entrada para clasificación
        batch=16,               # Tamaño del lote (puedes bajarlo a 8 si tu PC se pone muy lenta)
        device="cpu",           # Usa "cpu" (o cambia a 0 si tienes una tarjeta gráfica NVIDIA con CUDA)
        name="geriap_posture_model"
    )
    
    print("\n--------------------------------------------------")
    print("✅ ¡Entrenamiento completado con éxito!")
    print("Tu modelo entrenado está guardado en:")
    print("runs/classify/geriap_posture_model/weights/best.pt")
    print("--------------------------------------------------")

if __name__ == "__main__":
    entrenar()