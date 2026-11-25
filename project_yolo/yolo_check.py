import argparse
import shutil
import yaml
import torch
from pathlib import Path
from collections import Counter
from ultralytics import YOLO

ROOT = Path(r"C:\hyundai_project\construction-ppe\construction-ppe")
DST = ROOT.parent / "construction-ppe-5class"
PROJECT = Path(r"C:\hyundai_project\project_1")
RUNS = PROJECT / "runs" / "helmet_vest"
WEIGHTS = RUNS / "yolo26n_416" / "weights" / "best.pt"
DATA_YAML = DST / "data.yaml"

CLASS_MAP = {0: 0, 6: 1, 2: 2, 11: 3, 5: 4}
NAMES = ["helmet", "no_helmet", "vest", "no_vest", "person"]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

def prepare_dataset():
    for split in ["train", "val", "test"]:
        src_img = ROOT / "images" / split
        src_lbl = ROOT / "labels" / split
        dst_img = DST / "images" / split
        dst_lbl = DST / "labels" / split

        if not src_img.exists():
            if split == "test":
                continue
            raise FileNotFoundError(src_img)

        dst_img.mkdir(parents=True, exist_ok=True)
        dst_lbl.mkdir(parents=True, exist_ok=True)

        counts = Counter()
        num_images = 0

        for img in src_img.rglob("*"):
            if img.suffix.lower() not in IMAGE_EXTS:
                continue

            rel = img.relative_to(src_img)
            label = src_lbl / rel.with_suffix(".txt")
            new_img = dst_img / rel
            new_label = dst_lbl / rel.with_suffix(".txt")
            lines = []

            if label.exists():
                for line in label.read_text().splitlines():
                    parts = line.split()
                    if len(parts) != 5:
                        continue
                    cls = int(parts[0])
                    if cls in CLASS_MAP:
                        new_cls = CLASS_MAP[cls]
                        lines.append(f"{new_cls} " + " ".join(parts[1:]))
                        counts[new_cls] += 1

            new_img.parent.mkdir(parents=True, exist_ok=True)
            new_label.parent.mkdir(parents=True, exist_ok=True)
            if not new_img.exists():
                shutil.copy2(img, new_img)
            new_label.write_text("\n".join(lines))
            num_images += 1

        print(f"\n[{split}] Images: {num_images}")
        for i, name in enumerate(NAMES):
            print(f"  {name}: {counts[i]}")

    data = {
        "path": DST.as_posix(),
        "train": "images/train",
        "val": "images/val",
        "nc": len(NAMES),
        "names": NAMES
    }

    if (DST / "images" / "test").exists():
        data["test"] = "images/test"

    with open(DATA_YAML, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)

    print(f"\nDataset YAML: {DATA_YAML}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["prepare", "train", "val", "predict", "export"], default="train")
    parser.add_argument("--weights", default=None)
    parser.add_argument("--source", default="0")
    parser.add_argument("--device", default="0" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--imgsz", type=int, default=416)
    parser.add_argument("--conf", type=float, default=0.25)
    args = parser.parse_args()

    if args.mode == "prepare":
        prepare_dataset()
        return

    if args.mode == "train":
        prepare_dataset()
        model = YOLO(args.weights or "yolo26n.pt")
        model.train(
            data=str(DATA_YAML),
            epochs=args.epochs,
            batch=args.batch,
            imgsz=args.imgsz,
            device=args.device,
            workers=0,
            project=str(RUNS),
            name="yolo26n_416",
            patience=20,
            pretrained=True,
            exist_ok=True,
            plots=True
        )
    else:
        model = YOLO(args.weights or str(WEIGHTS))

        if args.mode == "val":
            model.val(data=str(DATA_YAML), imgsz=args.imgsz, device=args.device)

        elif args.mode == "predict":
            source = int(args.source) if args.source.isdigit() else args.source
            model.predict(
                source=source,
                imgsz=args.imgsz,
                device=args.device,
                conf=args.conf,
                show=True
            )

        elif args.mode == "export":
            model.export(format="onnx", imgsz=args.imgsz, device="cpu")

if __name__ == "__main__":
    main()