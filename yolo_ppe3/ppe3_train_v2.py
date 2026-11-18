"""PPE 3클래스 (helmet / head / vest) 학습 - 개선판

원본 yolo_robbin_test.py 대비 바뀐 점
  1. download  : 깨진 CLI 호출 제거, snapshot_download 직접 호출 + 재시도
  2. scan      : 라벨 누락 검사, 출처(ds1/ds2)별 클래스 분포, test 분할을 yaml에 포함
                 --oversample-head N 이면 head가 있는 학습 이미지를 N배로 늘린 목록 생성
  3. train     : 실행 이름을 명시(--name). 최신 best.pt 추측 안 함
  4. evaluate  : 클래스별 P / R / AP50 / AP50-95 출력 (head 미착용 성능 확인용)
                 val 또는 test 분할 선택, 결과를 JSON으로 저장
  5. bench     : 이미지를 메모리에 미리 올려 디스크 읽기 시간 제외, 단계별 시간 표시
  6. compare   : 여러 실행의 평가 JSON을 표 하나로 정리

사용법
    py -3.12 ppe3_train_v2.py --mode download
    py -3.12 ppe3_train_v2.py --mode scan [--oversample-head 3]
    py -3.12 ppe3_train_v2.py --mode train --imgsz 640 --epochs 20 --name v2_640
    py -3.12 ppe3_train_v2.py --mode evaluate --name v2_640 --split test
    py -3.12 ppe3_train_v2.py --mode bench --name v2_640 --imgsz 640
    py -3.12 ppe3_train_v2.py --mode compare --names yolov8n_320_e20 v2_640
"""

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "ppe3"
RUNS = BASE / "runs"
REPO = "Robbin123/ppe-dataset"
NAMES = ["helmet", "head", "vest"]
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
SPLITS = ("train", "val", "test")


def yaml_path(oversample):
    return BASE / (f"ppe3_v2_os{oversample}.yaml" if oversample > 1 else "ppe3_v2.yaml")


def images_of(split):
    d = DATA_DIR / split / "images"
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.suffix.lower() in IMG_EXT)


def label_of(img):
    return img.parent.parent / "labels" / (img.stem + ".txt")


def source_of(img):
    return img.name.split("_", 1)[0]          # ds1 / ds2


def read_classes(label_file):
    if not label_file.exists():
        return []
    out = []
    for line in label_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip():
            out.append(int(float(line.split()[0])))
    return out


# ───────────────────────── 다운로드 ─────────────────────────

def download(args):
    from huggingface_hub import snapshot_download

    for attempt in range(1, args.retries + 1):
        try:
            print(f"[{attempt}/{args.retries}] {REPO} → {DATA_DIR}")
            snapshot_download(repo_id=REPO, repo_type="dataset",
                              local_dir=str(DATA_DIR), max_workers=8)
            print("완료")
            return
        except Exception as e:                         # 네트워크·요청 제한
            print(f"실패: {type(e).__name__}: {e}")
            if attempt < args.retries:
                wait = 30 * attempt
                print(f"{wait}초 후 재시도")
                time.sleep(wait)
    raise SystemExit("다운로드 실패")


# ───────────────────────── 구조 확인 ─────────────────────────

def scan(args):
    print("── 분할별 장수 ──")
    problems = []
    train_imgs = []
    for split in SPLITS:
        imgs = images_of(split)
        missing = [p for p in imgs if not label_of(p).exists()]
        print(f"{split:5s} 이미지 {len(imgs):>6,}  라벨 없음 {len(missing):>5,}")
        if not imgs:
            problems.append(f"{split} 이미지 없음")
        elif missing:
            problems.append(f"{split} 라벨 없는 이미지 {len(missing)}장")
        if split == "train":
            train_imgs = imgs

    print("\n── train 출처별 클래스 분포 ──")
    dist = defaultdict(Counter)
    head_imgs = []
    for img in train_imgs:
        classes = read_classes(label_of(img))
        dist[source_of(img)].update(classes)
        if 1 in classes:
            head_imgs.append(img)
    total = Counter()
    for src in sorted(dist):
        total.update(dist[src])
        row = "  ".join(f"{NAMES[c]} {dist[src][c]:>6,}" for c in range(3))
        print(f"  {src}: {row}")
    s = sum(total.values()) or 1
    print("  합계: " + "  ".join(
        f"{NAMES[c]} {total[c]:>6,} ({total[c] / s * 100:4.1f}%)" for c in range(3)))
    print(f"  head가 있는 학습 이미지: {len(head_imgs):,}장")
    print("  ※ head는 ds1에만, vest는 ds2에만 라벨이 있습니다.")

    train_entry = "train/images"
    if args.oversample_head > 1:
        lst = DATA_DIR / f"train_os{args.oversample_head}.txt"
        lines = [str(p) for p in train_imgs]
        lines += [str(p) for p in head_imgs] * (args.oversample_head - 1)
        lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
        train_entry = lst.name
        print(f"\nhead 오버샘플링 x{args.oversample_head}: "
              f"{len(train_imgs):,} → {len(lines):,}장 ({lst.name})")

    cfg = {
        "path": str(DATA_DIR).replace("\\", "/"),
        "train": train_entry,
        "val": "val/images",
        "test": "test/images",
        "nc": len(NAMES),
        "names": NAMES,
    }
    out = yaml_path(args.oversample_head)
    out.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")
    print(f"\n생성: {out.name}")

    if problems:
        print("\n[문제]")
        for p in problems:
            print("  -", p)
        raise SystemExit(1)


# ───────────────────────── 학습 ─────────────────────────

def train(args):
    from ultralytics import YOLO

    data = yaml_path(args.oversample_head)
    if not data.exists():
        raise SystemExit(f"{data.name} 없음. 먼저 --mode scan")
    name = args.name or f"v2_{args.model}_{args.imgsz}_e{args.epochs}"
    print(f"{name}: {args.model} | {args.imgsz}px | batch {args.batch} | "
          f"{args.epochs} epochs | data {data.name}")

    start = time.perf_counter()
    YOLO(f"{args.model}.pt").train(
        data=str(data), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
        device=args.device, project=str(RUNS), name=name, exist_ok=True,
        patience=args.patience, workers=args.workers, cache=args.cache,
        seed=0, verbose=True,
    )
    elapsed = time.perf_counter() - start
    (RUNS / name / "train_time.json").write_text(
        json.dumps({"seconds": elapsed}), encoding="utf-8")
    print(f"\n총 학습 시간: {elapsed / 60:.1f}분")
    print(f"가중치: {RUNS / name / 'weights' / 'best.pt'}")


# ───────────────────────── 평가 ─────────────────────────

def weights_of(args):
    if args.weights:
        p = Path(args.weights)
    elif args.name:
        p = RUNS / args.name / "weights" / "best.pt"
    else:
        raise SystemExit("--name 또는 --weights를 지정하세요.")
    if not p.exists():
        raise SystemExit(f"가중치 없음: {p}")
    return p


def run_dir_of(args, w):
    return RUNS / args.name if args.name else w.parent.parent


def evaluate(args):
    from ultralytics import YOLO

    w = weights_of(args)
    data = yaml_path(1)
    if not data.exists():
        raise SystemExit(f"{data.name} 없음. 먼저 --mode scan")
    print(f"가중치: {w} | split {args.split} | {args.imgsz}px")
    m = YOLO(str(w)).val(data=str(data), split=args.split, imgsz=args.imgsz,
                         batch=args.batch, device=args.device, plots=False,
                         project=str(RUNS), name="_eval", exist_ok=True)

    b = m.box
    per_class = {}
    print(f"\n{'class':8s} {'P':>6s} {'R':>6s} {'AP50':>6s} {'AP50-95':>8s}")
    for i, c in enumerate(b.ap_class_index):
        name = m.names[int(c)]
        p, r, ap50, ap = b.class_result(i)
        per_class[name] = {"P": p, "R": r, "AP50": ap50, "AP50-95": ap}
        print(f"{name:8s} {p:6.3f} {r:6.3f} {ap50:6.3f} {ap:8.3f}")
    print(f"{'all':8s} {b.mp:6.3f} {b.mr:6.3f} {b.map50:6.3f} {b.map:8.3f}")

    result = {"weights": str(w), "split": args.split, "imgsz": args.imgsz,
              "P": b.mp, "R": b.mr, "mAP50": b.map50, "mAP50-95": b.map,
              "per_class": per_class, "speed_ms": m.speed}
    out = run_dir_of(args, w) / f"eval_{args.split}_{args.imgsz}.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n저장: {out}")


# ───────────────────────── 속도 ─────────────────────────

def bench(args):
    import cv2
    from ultralytics import YOLO

    w = weights_of(args)
    model = YOLO(str(w))
    img_path = Path(args.image) if Path(args.image).exists() else images_of("test")[0]
    frame = cv2.imread(str(img_path))          # 디스크 읽기는 측정에서 제외

    kw = dict(imgsz=args.imgsz, device=args.device, verbose=False)
    for _ in range(10):
        model.predict(frame, **kw)

    times, stages = [], defaultdict(float)
    for _ in range(args.runs):
        t = time.perf_counter()
        r = model.predict(frame, **kw)[0]
        times.append(time.perf_counter() - t)
        for k, v in r.speed.items():
            stages[k] += v
    times.sort()
    mean = sum(times) / len(times)
    stage_ms = {k: v / args.runs for k, v in stages.items()}

    print(f"\n{w.parent.parent.name} | {args.imgsz}px | {args.runs}회 | "
          f"device {args.device} | {img_path.name}")
    print(f"평균  : {mean * 1000:6.1f} ms → {1 / mean:7.1f} FPS")
    print(f"중앙값: {times[len(times) // 2] * 1000:6.1f} ms")
    print("단계별: " + ", ".join(f"{k} {v:.2f}ms" for k, v in stage_ms.items()))

    out = run_dir_of(args, w) / f"bench_{args.imgsz}_{args.device}.json"
    out.write_text(json.dumps({"mean_ms": mean * 1000, "fps": 1 / mean,
                               "median_ms": times[len(times) // 2] * 1000,
                               "stages_ms": stage_ms}, indent=2), encoding="utf-8")
    print(f"저장: {out}")


# ───────────────────────── 비교 ─────────────────────────

def compare(args):
    head = ("run", "imgsz", "mAP50", "mAP50-95", "head R", "head AP50",
            "FPS", "학습(분)")
    rows = []
    for name in args.names:
        d = RUNS / name
        ev = sorted(d.glob(f"eval_{args.split}_*.json"))
        if not ev:
            print(f"[건너뜀] {name}: eval_{args.split} 없음")
            continue
        e = json.loads(ev[-1].read_text(encoding="utf-8"))
        bn = sorted(d.glob(f"bench_{e['imgsz']}_*.json"))
        fps = json.loads(bn[-1].read_text(encoding="utf-8"))["fps"] if bn else None
        tt = d / "train_time.json"
        mins = json.loads(tt.read_text(encoding="utf-8"))["seconds"] / 60 if tt.exists() else None
        h = e["per_class"].get("head", {})
        rows.append((name, e["imgsz"], f"{e['mAP50']:.3f}", f"{e['mAP50-95']:.3f}",
                     f"{h.get('R', 0):.3f}", f"{h.get('AP50', 0):.3f}",
                     f"{fps:.1f}" if fps else "-", f"{mins:.0f}" if mins else "-"))
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for r in rows:
        print("| " + " | ".join(str(c) for c in r) + " |")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="PPE 3클래스 학습 (개선판)")
    p.add_argument("--mode", default="scan",
                   choices=["download", "scan", "train", "evaluate", "bench", "compare"])
    p.add_argument("--model", default="yolov8n")
    p.add_argument("--name", default=None, help="runs/ 아래 실행 이름")
    p.add_argument("--names", nargs="*", default=[], help="compare 대상")
    p.add_argument("--weights", default=None)
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--device", default="0", help="0=GPU, cpu=CPU")
    p.add_argument("--patience", type=int, default=20)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--cache", action="store_true")
    p.add_argument("--oversample-head", type=int, default=1)
    p.add_argument("--split", default="test", choices=["val", "test"])
    p.add_argument("--image", default="test.jpg")
    p.add_argument("--runs", type=int, default=200)
    p.add_argument("--retries", type=int, default=5)
    args = p.parse_args()

    {"download": download, "scan": scan, "train": train, "evaluate": evaluate,
     "bench": bench, "compare": compare}[args.mode](args)
