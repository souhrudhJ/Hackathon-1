"""
Train YOLOv8 on the 5-class wall defect dataset from Roboflow.
Classes: crack, water_seepage, mold, peeling_paint, stairstep_crack

Run this on Google Colab (free GPU) or locally with a CUDA GPU.
After training, copy runs/detect/train/weights/best.pt -> weights/best.pt

Usage:
    python train.py                     # default: 50 epochs, yolov8n
    python train.py --epochs 10         # quick test
    python train.py --model yolov8s.pt  # larger model
"""
import argparse
import os
import shutil

def main():
    parser = argparse.ArgumentParser(description="Train YOLOv8 on wall defect dataset")
    parser.add_argument("--epochs", type=int, default=50, help="Training epochs")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="Base model (yolov8n/s/m/l)")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size")
    args = parser.parse_args()

    # 1. Download dataset from Roboflow
    print("=" * 60)
    print("Step 1: Downloading wall defect dataset from Roboflow...")
    print("=" * 60)
    from roboflow import Roboflow
    rf = Roboflow(api_key=os.getenv("ROBOFLOW_API_KEY", ""))
    project = rf.workspace("objectdetection-qxiqx").project("detr_crack_dataset")
    version = project.version(1)
    dataset = version.download("yolov8")
    data_yaml = os.path.join(dataset.location, "data.yaml")
    print(f"Dataset downloaded to: {dataset.location}")
    print(f"data.yaml: {data_yaml}")

    # 2. Train YOLOv8
    print("=" * 60)
    print(f"Step 2: Training YOLOv8 ({args.model}) for {args.epochs} epochs...")
    print("=" * 60)
    from ultralytics import YOLO
    model = YOLO(args.model)
    results = model.train(
        data=data_yaml,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        project="runs/detect",
        name="train",
        exist_ok=True,
        verbose=True,
    )

    # 3. Copy best weights
    trained_weights = os.path.join("runs", "detect", "train", "weights", "best.pt")
    dest = os.path.join("weights", "best.pt")
    if os.path.isfile(trained_weights):
        os.makedirs("weights", exist_ok=True)
        shutil.copy2(trained_weights, dest)
        print("=" * 60)
        print(f"Done! Best weights copied to: {dest}")
        print("Restart the Streamlit app to use the new model.")
        print("=" * 60)
    else:
        print(f"Warning: {trained_weights} not found. Check training output.")

if __name__ == "__main__":
    main()
