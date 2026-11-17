"""YOLOv8 학습 + Faster R-CNN과 비교

사용법
    py -3.12 yolo_compare.py --mode setup              # data.yaml 점검·생성
    py -3.12 yolo_compare.py --mode train --epochs 50  # 학습
    py -3.12 yolo_compare.py --mode bench              # 속도 측정
    py -3.12 yolo_compare.py --mode predict --image a.jpg
    py -3.12 yolo_compare.py --mode table              # 비교표 출력

설치
    py -3.12 -m pip install ultralytics
"""

import argparse
import time
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "construction-ppe"
YAML_PATH = DATA_DIR / "data.yaml"
YOLO_YAML = BASE / "ppe_yolo.yaml"          # YOLO 전용으로 새로 쓴 것
RUNS = BASE / "runs"


def setup(args):
    """data.yaml을 읽어 YOLO가 요구하는 형식으로 다시 쓴다."""
    if not YAML_PATH.exists():
        raise FileNotFoundError(f"없습니다: {YAML_PATH}")

    with open(YAML_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    names = cfg["names"]
    if isinstance(names, dict):
        names = [names[i] for i in sorted(map(int, names))]

    train_dir = DATA_DIR / "images" / "train"
    val_dir = DATA_DIR / "images" / "val"

    for d in (train_dir, val_dir):
        n = len(list(d.glob("*.jpg"))) + len(list(d.glob("*.png"))) \
            + len(list(d.glob("*.jpeg")))
        print(f"{d.name}: {n}장")

    new_cfg = {
        "path": str(DATA_DIR).replace("\\", "/"),
        "train": "images/train",
        "val": "images/val",
        "nc": len(names),
        "names": names,
    }

    with open(YOLO_YAML, "w", encoding="utf-8") as f:
        yaml.safe_dump(new_cfg, f, allow_unicode=True, sort_keys=False)

    print(f"\n생성: {YOLO_YAML}")
    print(f"클래스 {len(names)}개: {names}")
    print("\n다음 단계:")
    print("  py -3.12 yolo_compare.py --mode train --epochs 50")


def train(args):
    from ultralytics import YOLO

    if not YOLO_YAML.exists():
        print("먼저 setup을 실행하세요.")
        return

    model = YOLO(f"{args.model}.pt")
    print(f"모델: {args.model} | 해상도: {args.imgsz} | epochs: {args.epochs}")

    start = time.perf_counter()
    model.train(
        data=str(YOLO_YAML),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=0,                    # GPU. CPU면 'cpu'
        project=str(RUNS),
        name=f"{args.model}_{args.imgsz}",
        exist_ok=True,
        patience=20,                 # 개선 없으면 조기 종료
        verbose=True,
    )
    elapsed = time.perf_counter() - start

    print(f"\n총 학습 시간: {elapsed / 60:.1f}분")
    print(f"가중치: {RUNS}/{args.model}_{args.imgsz}/weights/best.pt")


def find_weights(args):
    path = Path(args.weights) if args.weights else \
        RUNS / f"{args.model}_{args.imgsz}" / "weights" / "best.pt"
    if not path.exists():
        raise FileNotFoundError(f"가중치가 없습니다: {path}\n먼저 학습하세요.")
    return path


def bench(args):
    """같은 이미지를 반복 추론해 평균 FPS를 낸다."""
    from ultralytics import YOLO

    model = YOLO(str(find_weights(args)))

    img = Path(args.image) if Path(args.image).exists() else None
    if img is None:
        candidates = sorted((DATA_DIR / "images" / "val").glob("*.jpg"))
        if not candidates:
            raise ValueError("테스트할 이미지가 없습니다.")
        img = candidates[0]
        print(f"[안내] val 첫 이미지 사용: {img.name}")

    for _ in range(5):                       # 워밍업
        model.predict(str(img), verbose=False, device=0)

    times = []
    for _ in range(args.runs):
        start = time.perf_counter()
        model.predict(str(img), verbose=False, device=0)
        times.append(time.perf_counter() - start)

    times.sort()
    mean = sum(times) / len(times)
    print(f"\n모델: {args.model} | 해상도: {args.imgsz} | {args.runs}회")
    print(f"평균  : {mean * 1000:6.1f} ms  →  {1 / mean:6.2f} FPS")
    print(f"중앙값: {times[len(times) // 2] * 1000:6.1f} ms")
    print(f"최소  : {times[0] * 1000:6.1f} ms")


def val(args):
    """mAP 측정."""
    from ultralytics import YOLO

    model = YOLO(str(find_weights(args)))
    metrics = model.val(data=str(YOLO_YAML), imgsz=args.imgsz, device=0)

    print(f"\nmAP@0.5      : {metrics.box.map50:.4f}")
    print(f"mAP@0.5:0.95 : {metrics.box.map:.4f}")
    print(f"Precision    : {metrics.box.mp:.4f}")
    print(f"Recall       : {metrics.box.mr:.4f}")


def predict(args):
    from ultralytics import YOLO

    model = YOLO(str(find_weights(args)))
    results = model.predict(
        args.image,
        conf=args.conf,
        imgsz=args.imgsz,
        save=True,
        project=str(RUNS),
        name="predict",
        exist_ok=True,
        device=0,
    )

    r = results[0]
    print(f"\n탐지: {len(r.boxes)}개")
    for box in r.boxes:
        cls = int(box.cls)
        print(f"  {r.names[cls]:12s} {float(box.conf):.2f}")
    print(f"저장: {RUNS}/predict/")


def table(args):
    """실험 결과를 표로 출력 (직접 채워 넣는 양식)."""
    rows = [
        ("0. 기준선", "MobileNetV4+FasterRCNN 640", "", "", ""),
        ("1. 해상도", "MobileNetV4+FasterRCNN 320", "", "", ""),
        ("2. 증강", "+ flip/brightness", "", "", ""),
        ("3. 모델", "YOLOv8n 320", "", "", ""),
        ("4. 양자화", "YOLOv8n INT8", "", "", ""),
    ]
    w = (12, 30, 10, 10, 10)
    head = ("단계", "설정", "mAP@0.5", "FPS(PC)", "FPS(Pi)")

    line = "+".join("-" * (x + 2) for x in w)
    print(line)
    print(" | ".join(h.ljust(x) for h, x in zip(head, w)))
    print(line)
    for row in rows:
        print(" | ".join(str(c).ljust(x) for c, x in zip(row, w)))
    print(line)
    print("\n빈칸은 각 모드를 돌려서 채우세요.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="YOLO 학습·비교")
    p.add_argument("--mode",
                   choices=["setup", "train", "bench", "val", "predict", "table"],
                   default="setup")
    p.add_argument("--model", default="yolov8n",
                   help="yolov8n / yolov8s / yolov11n 등")
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--imgsz", type=int, default=320)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--conf", type=float, default=0.3)
    p.add_argument("--image", default="test.jpg")
    p.add_argument("--runs", type=int, default=100)
    p.add_argument("--weights", default=None)
    args = p.parse_args()

    {"setup": setup, "train": train, "bench": bench,
     "val": val, "predict": predict, "table": table}[args.mode](args)
