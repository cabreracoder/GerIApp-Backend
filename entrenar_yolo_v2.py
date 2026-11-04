
from ultralytics import YOLO

def entrenar():
    print("Iniciando entrenamiento YOLO11n-cls...")
    print("Dataset: dataset_final_yolo_v2")

    model = YOLO("yolo11n-cls.pt")

    model.train(
        data="dataset_posturas/dataset_final_yolo_v2",
        epochs=200,
        patience=100,
        batch=16,
        imgsz=640,
        optimizer="auto",
        pretrained=True,
        seed=0,
        deterministic=True,
        device="cpu",
        workers=4,
        project="runs/classify",
        name="train-4",
        exist_ok=False
    )

    print("Entrenamiento finalizado.")
    print("Modelo:", "runs/classify/train-4/weights/best.pt")


if __name__ == "__main__":
    entrenar()
