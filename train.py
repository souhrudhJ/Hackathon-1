"""
===============================================================================
  PROPERTY DEFECT MODEL TRAINER
  Train YOLOv8 on the 5-class wall defect dataset.
  Classes: crack, water_seepage, mold, peeling_paint, stairstep_crack
===============================================================================

INSTRUCTIONS FOR THE PERSON WITH THE GPU:

  1. Clone the repo:
       git clone https://github.com/souhrudhJ/Hackathon-1.git
       cd Hackathon-1

  2. Install dependencies:
       pip install ultralytics roboflow

  3. Run training:
       python train.py                  # default: 50 epochs, yolov8n
       python train.py --epochs 25      # faster training
       python train.py --model yolov8s.pt --epochs 50   # better accuracy

  4. After training completes, copy weights/best.pt back to the main machine.

  Training takes ~15-20 min on a decent GPU (RTX 3060+), ~25-30 min on older.
  The script auto-downloads the dataset, trains, validates, and saves weights.

===============================================================================
"""
import argparse
import os
import shutil
import sys
import time


def check_gpu():
    """Check if CUDA GPU is available."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            mem = torch.cuda.get_device_properties(0).total_mem / 1e9
            print(f"  GPU: {name} ({mem:.1f} GB)")
            return True
        else:
            print("  GPU: None (will use CPU — training will be SLOW)")
            return False
    except ImportError:
        print("  PyTorch not installed yet (ultralytics will install it)")
        return False


def download_dataset():
    """Download the 5-class defect dataset from Roboflow."""
    from roboflow import Roboflow

    print("\n  Downloading from Roboflow (objectdetection-qxiqx/detr_crack_dataset)...")
    rf = Roboflow(api_key="XdP8NQpTT2okkMBxTP0r")
    project = rf.workspace("objectdetection-qxiqx").project("detr_crack_dataset")
    version = project.version(1)
    dataset = version.download("yolov8")

    data_yaml = os.path.join(dataset.location, "data.yaml")
    print(f"  Dataset: {dataset.location}")
    print(f"  data.yaml: {data_yaml}")

    # Print dataset info
    if os.path.isfile(data_yaml):
        with open(data_yaml, "r") as f:
            print(f"\n  --- data.yaml ---")
            print("  " + "  ".join(f.readlines()))
            print("  -----------------")

    return data_yaml


def train_model(data_yaml: str, args):
    """Train YOLOv8 on the defect dataset."""
    from ultralytics import YOLO

    print(f"\n  Base model: {args.model}")
    print(f"  Epochs: {args.epochs}")
    print(f"  Batch size: {args.batch}")
    print(f"  Image size: {args.imgsz}")
    print(f"  Device: {'cuda' if args.device == 'auto' else args.device}")

    model = YOLO(args.model)

    device = None if args.device == "auto" else args.device

    results = model.train(
        data=data_yaml,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        project="runs/detect",
        name="defect_model",
        exist_ok=True,
        verbose=True,
        device=device,
        patience=15,        # early stopping
        save=True,
        save_period=10,      # checkpoint every 10 epochs
        plots=True,
    )

    return results


def validate_model():
    """Run validation on the trained model and print results."""
    from ultralytics import YOLO

    weights = os.path.join("runs", "detect", "defect_model", "weights", "best.pt")
    if not os.path.isfile(weights):
        print("  Skipping validation — best.pt not found")
        return

    print(f"\n  Validating {weights}...")
    model = YOLO(weights)
    print(f"  Classes: {model.names}")
    metrics = model.val(verbose=False)
    print(f"  mAP50: {metrics.box.map50:.4f}")
    print(f"  mAP50-95: {metrics.box.map:.4f}")


def copy_weights():
    """Copy best.pt to weights/ folder."""
    src = os.path.join("runs", "detect", "defect_model", "weights", "best.pt")
    dst = os.path.join("weights", "best.pt")

    if os.path.isfile(src):
        os.makedirs("weights", exist_ok=True)
        shutil.copy2(src, dst)
        size_mb = os.path.getsize(dst) / 1e6
        print(f"\n  Copied: {src}")
        print(f"      ->  {dst} ({size_mb:.1f} MB)")
        return dst
    else:
        print(f"\n  WARNING: {src} not found!")
        # Check if there's a last.pt instead
        last = os.path.join("runs", "detect", "defect_model", "weights", "last.pt")
        if os.path.isfile(last):
            os.makedirs("weights", exist_ok=True)
            shutil.copy2(last, dst)
            print(f"  Used last.pt instead -> {dst}")
            return dst
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Train YOLOv8 defect detection model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--epochs", type=int, default=50, help="Training epochs (default: 50)")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="Base model: yolov8n/s/m/l.pt (default: yolov8n.pt)")
    parser.add_argument("--batch", type=int, default=16, help="Batch size (default: 16, lower if OOM)")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size (default: 640)")
    parser.add_argument("--device", type=str, default="auto", help="Device: auto, 0, cpu (default: auto)")
    args = parser.parse_args()

    print("=" * 60)
    print("  PROPERTY DEFECT MODEL TRAINER")
    print("  YOLOv8 + 5-class wall defect dataset")
    print("=" * 60)

    # Step 0: Check environment
    print("\n[0/4] Checking environment...")
    check_gpu()
    print(f"  Python: {sys.version.split()[0]}")

    # Step 1: Download dataset
    print("\n[1/4] Downloading dataset...")
    start = time.time()
    data_yaml = download_dataset()
    print(f"  Done in {time.time() - start:.0f}s")

    # Step 2: Train
    print("\n[2/4] Training model...")
    print("-" * 60)
    start = time.time()
    train_model(data_yaml, args)
    elapsed = time.time() - start
    print("-" * 60)
    print(f"  Training done in {elapsed / 60:.1f} minutes")

    # Step 3: Validate
    print("\n[3/4] Validating model...")
    validate_model()

    # Step 4: Copy weights
    print("\n[4/4] Copying weights...")
    dst = copy_weights()

    # Done
    print("\n" + "=" * 60)
    if dst:
        print("  TRAINING COMPLETE!")
        print(f"  Model saved to: {dst}")
        print()
        print("  NEXT STEPS:")
        print(f"  1. Copy '{dst}' to the main machine")
        print("  2. Put it in the Hackathon/weights/ folder")
        print("  3. The app will auto-detect and use it")
    else:
        print("  Training finished but weights not found.")
        print("  Check the runs/detect/defect_model/ folder manually.")
    print("=" * 60)


if __name__ == "__main__":
    main()
