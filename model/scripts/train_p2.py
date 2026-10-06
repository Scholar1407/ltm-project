import os
import sys
import argparse
from pathlib import Path

# Ensure UTF-8 output encoding
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_YAML = BASE_DIR / "dataset" / "data.yaml"

def train_p2(
    epochs=100,
    batch=-1,
    device=None,
    resume=False,
    data=str(DATA_YAML),
    imgsz=640,
    save_period=5,
    patience=20,
):
    print("=" * 70)
    print("       PHASE 2: TRAIN PRIMARY MODEL (YOLOv8s-P2)")
    print("=" * 70)
    
    from ultralytics import YOLO
    import torch

    has_cuda = torch.cuda.is_available()
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA Available: {has_cuda}")
    if has_cuda:
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        amp = True
        chosen_device = device if device is not None else 0
        chosen_batch = batch
    else:
        print("Note: Running on CPU. Disabling AMP, using batch size.")
        amp = False
        chosen_device = "cpu"
        chosen_batch = 16 if batch == -1 else batch

    weights_last = BASE_DIR / "runs" / "detect" / "smoke_p2" / "weights" / "last.pt"

    if resume and weights_last.exists():
        print(f"Resuming training from checkpoint: {weights_last}")
        model = YOLO(str(weights_last))
        model.train(resume=True)
    else:
        print("Starting new YOLOv8s-P2 training run...")
        try:
            model = YOLO("yolov8s-p2.yaml").load("yolov8s-p2.pt")
            print("Loaded yolov8s-p2.pt weights.")
        except Exception as e:
            print(f"yolov8s-p2.pt unavailable ({e}), loading yolov8s.pt backbone into yolov8s-p2.yaml...")
            model = YOLO("yolov8s-p2.yaml").load("yolov8s.pt")

        model.train(
            data=data,
            epochs=epochs,
            imgsz=imgsz,
            batch=chosen_batch,
            amp=amp,
            device=chosen_device,
            save_period=save_period,
            patience=patience,
            name="smoke_p2",
            project=str(BASE_DIR / "runs" / "detect"),
            exist_ok=True,
            plots=True,
            verbose=True,
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=-1)
    parser.add_argument("--device", type=str, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--data", type=str, default=str(DATA_YAML))
    parser.add_argument("--imgsz", type=int, default=640)
    args = parser.parse_args()

    train_p2(
        epochs=args.epochs,
        batch=args.batch,
        device=args.device,
        resume=args.resume,
        data=args.data,
        imgsz=args.imgsz,
    )
