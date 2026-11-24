<<<<<<< HEAD

import argparse
import time
from collections import OrderedDict
from pathlib import Path

import timm
import torch
import yaml
from PIL import Image, ImageDraw
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision.models.detection import FasterRCNN
from torchvision.models.detection.anchor_utils import AnchorGenerator
from torchvision.ops import FeaturePyramidNetwork, MultiScaleRoIAlign
from torchvision.transforms.functional import to_tensor

DATA_ROOT = Path(r"C:\hyundai_project\construction-ppe\construction-ppe")
WEIGHTS = Path("weights/mobilenetv4_ppe.pth")
MODEL_NAME = "mobilenetv4_conv_small.e2400_r224_in1k"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def read_classes():
    with open(DATA_ROOT / "data.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    names = config["names"]
    if isinstance(names, dict):
        names = {int(k): str(v) for k, v in names.items()}
        if sorted(names) != list(range(len(names))):
            raise ValueError("data.yaml 클래스 ID가 0부터 연속적이어야 합니다.")
        return [names[i] for i in range(len(names))]
    return [str(name) for name in names]


class PPEData(Dataset):
    def __init__(self, split, class_count):
        self.img_dir = DATA_ROOT / "images" / split
        self.label_dir = DATA_ROOT / "labels" / split
        self.class_count = class_count
        self.images = sorted(
            p for p in self.img_dir.iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )
        if not self.images:
            raise ValueError(f"이미지가 없습니다: {self.img_dir}")

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        path = self.images[idx]
        image = Image.open(path).convert("RGB")
        W, H = image.size
        label_path = self.label_dir / (path.stem + ".txt")
        boxes, labels = [], []

        if label_path.exists():
            for line in label_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) != 5:
                    raise ValueError(f"잘못된 라벨: {label_path}: {line}")
                cls_float, xc, yc, w, h = map(float, parts)
                cls = int(cls_float)
                if cls_float != cls or not 0 <= cls < self.class_count:
                    raise ValueError(f"잘못된 클래스 ID: {label_path}: {cls_float}")
                x1 = max(0.0, (xc - w / 2) * W)
                y1 = max(0.0, (yc - h / 2) * H)
                x2 = min(float(W), (xc + w / 2) * W)
                y2 = min(float(H), (yc + h / 2) * H)
                if x2 <= x1 or y2 <= y1:
                    continue
                boxes.append([x1, y1, x2, y2])
                labels.append(cls + 1)  # Faster R-CNN: 0 = background

        target = {
            "boxes": torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4),
            "labels": torch.tensor(labels, dtype=torch.int64)
        }
        return to_tensor(image), target


class MobileNetV4FPN(nn.Module):
    def __init__(self, pretrained=True):
        super().__init__()
        self.encoder = timm.create_model(
            MODEL_NAME,
            pretrained=pretrained,
            features_only=True,
            out_indices=(2, 3, 4)
        )
        channels = self.encoder.feature_info.channels()
        self.fpn = FeaturePyramidNetwork(channels, out_channels=128)
        self.out_channels = 128

    def forward(self, x):
        features = self.encoder(x)
        features = OrderedDict((str(i), f) for i, f in enumerate(features))
        return self.fpn(features)


def build_model(num_classes, pretrained=True):
    backbone = MobileNetV4FPN(pretrained)
    anchor_generator = AnchorGenerator(
        sizes=((16, 32), (32, 64), (64, 128)),
        aspect_ratios=((0.5, 1.0, 2.0),) * 3
    )
    roi_pool = MultiScaleRoIAlign(
        featmap_names=["0", "1", "2"],
        output_size=7,
        sampling_ratio=2
    )
    return FasterRCNN(
        backbone,
        num_classes=num_classes + 1,
        rpn_anchor_generator=anchor_generator,
        box_roi_pool=roi_pool,
        min_size=320,
        max_size=640,
        image_mean=[0.485, 0.456, 0.406],
        image_std=[0.229, 0.224, 0.225]
    )


def collate_fn(batch):
    return tuple(zip(*batch))


def check(classes):
    dataset = PPEData("train", len(classes))
    print("Device:", DEVICE)
    print("Classes:", list(enumerate(classes)))
    print("Train images:", len(dataset))
    try:
        val_dataset = PPEData("val", len(classes))
        print("Val images:", len(val_dataset))
    except ValueError:
        print("Val images: 0")

    image, target = dataset[0]
    print("Sample:", dataset.images[0].name)
    print("Image shape:", tuple(image.shape))
    print("Boxes:", tuple(target["boxes"].shape))
    print("Labels:", target["labels"].tolist())

    model = build_model(len(classes), pretrained=True).to(DEVICE)
    model.eval()
    with torch.inference_mode():
        features = model.backbone(
            torch.randn(1, 3, 320, 320, device=DEVICE)
        )
        for name, feat in features.items():
            print(f"FPN {name}: {tuple(feat.shape)}")
        output = model([image.to(DEVICE)])[0]
    print("Prediction shape:", tuple(output["boxes"].shape))


def train(args, classes):
    train_dataset = PPEData("train", len(classes))
    loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
        collate_fn=collate_fn
    )
    model = build_model(len(classes), pretrained=True).to(DEVICE)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    WEIGHTS.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        start = time.perf_counter()

        for images, targets in loader:
            images = [img.to(DEVICE) for img in images]
            targets = [
                {key: value.to(DEVICE) for key, value in t.items()}
                for t in targets
            ]
            losses = model(images, targets)
            loss = sum(losses.values())
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        avg_loss = total_loss / len(loader)
        elapsed = time.perf_counter() - start
        print(
            f"Epoch {epoch + 1}/{args.epochs} | "
            f"Loss: {avg_loss:.4f} | Time: {elapsed:.1f}s"
        )
        torch.save({
            "model": model.state_dict(),
            "classes": classes,
            "epoch": epoch + 1
        }, WEIGHTS)

    print("Saved:", WEIGHTS)


def predict(args, classes):
    checkpoint = torch.load(WEIGHTS, map_location="cpu", weights_only=True)
    if checkpoint["classes"] != classes:
        raise ValueError("체크포인트 클래스와 data.yaml이 다릅니다.")

    model = build_model(len(classes), pretrained=False)
    model.load_state_dict(checkpoint["model"])
    model = model.to(DEVICE).eval()

    image = Image.open(args.image).convert("RGB")
    tensor = to_tensor(image).to(DEVICE)

    with torch.inference_mode():
        if DEVICE.type == "cuda":
            torch.cuda.synchronize()
        start = time.perf_counter()
        output = model([tensor])[0]
        if DEVICE.type == "cuda":
            torch.cuda.synchronize()
        elapsed = time.perf_counter() - start

    draw = ImageDraw.Draw(image)
    count = 0
    for box, label, score in zip(
        output["boxes"].cpu(),
        output["labels"].cpu(),
        output["scores"].cpu()
    ):
        if float(score) < args.conf:
            continue
        xyxy = [float(v) for v in box]
        name = classes[int(label) - 1]
        draw.rectangle(xyxy, outline="red", width=3)
        draw.text(
            (xyxy[0], xyxy[1]),
            f"{name} {float(score):.2f}",
            fill="red"
        )
        count += 1

    image.save(args.output)
    print(f"Detections: {count}")
    print(f"Latency: {elapsed * 1000:.1f} ms")
    print(f"FPS (single-image estimate): {1 / elapsed:.2f}")
    print("Saved:", args.output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=["check", "train", "predict"], default="check"
    )
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--lr", type=float, default=0.0001)
    parser.add_argument("--image", type=str, default="test.jpg")
    parser.add_argument("--output", type=str, default="result.jpg")
    parser.add_argument("--conf", type=float, default=0.5)
    args = parser.parse_args()

    classes = read_classes()
    if args.mode == "check":
        check(classes)
    elif args.mode == "train":
        train(args, classes)
    else:
        predict(args, classes)
=======

import argparse
import time
from collections import OrderedDict
from pathlib import Path

import timm
import torch
import yaml
import statistics
from PIL import Image, ImageDraw
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision.models.detection import FasterRCNN
from torchvision.models.detection.anchor_utils import AnchorGenerator
from torchvision.ops import FeaturePyramidNetwork, MultiScaleRoIAlign
from torchvision.transforms.functional import to_tensor

DATA_ROOT = Path(r"C:\hyundai_project\construction-ppe\construction-ppe")
WEIGHTS = Path("weights/mobilenetv4_ppe.pth")
MODEL_NAME = "mobilenetv4_conv_small.e2400_r224_in1k"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def read_classes():
    with open(DATA_ROOT / "data.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    names = config["names"]
    if isinstance(names, dict):
        names = {int(k): str(v) for k, v in names.items()}
        if sorted(names) != list(range(len(names))):
            raise ValueError("data.yaml 클래스 ID가 0부터 연속적이어야 합니다.")
        return [names[i] for i in range(len(names))]
    return [str(name) for name in names]


class PPEData(Dataset):
    def __init__(self, split, class_count):
        self.img_dir = DATA_ROOT / "images" / split
        self.label_dir = DATA_ROOT / "labels" / split
        self.class_count = class_count
        self.images = sorted(
            p for p in self.img_dir.iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )
        if not self.images:
            raise ValueError(f"이미지가 없습니다: {self.img_dir}")

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        path = self.images[idx]
        image = Image.open(path).convert("RGB")
        W, H = image.size
        label_path = self.label_dir / (path.stem + ".txt")
        boxes, labels = [], []

        if label_path.exists():
            for line in label_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) != 5:
                    raise ValueError(f"잘못된 라벨: {label_path}: {line}")
                cls_float, xc, yc, w, h = map(float, parts)
                cls = int(cls_float)
                if cls_float != cls or not 0 <= cls < self.class_count:
                    raise ValueError(f"잘못된 클래스 ID: {label_path}: {cls_float}")
                x1 = max(0.0, (xc - w / 2) * W)
                y1 = max(0.0, (yc - h / 2) * H)
                x2 = min(float(W), (xc + w / 2) * W)
                y2 = min(float(H), (yc + h / 2) * H)
                if x2 <= x1 or y2 <= y1:
                    continue
                boxes.append([x1, y1, x2, y2])
                labels.append(cls + 1)  # Faster R-CNN: 0 = background

        target = {
            "boxes": torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4),
            "labels": torch.tensor(labels, dtype=torch.int64)
        }
        return to_tensor(image), target


class MobileNetV4FPN(nn.Module):
    def __init__(self, pretrained=True):
        super().__init__()
        self.encoder = timm.create_model(
            MODEL_NAME,
            pretrained=pretrained,
            features_only=True,
            out_indices=(2, 3, 4)
        )
        channels = self.encoder.feature_info.channels()
        self.fpn = FeaturePyramidNetwork(channels, out_channels=128)
        self.out_channels = 128

    def forward(self, x):
        features = self.encoder(x)
        features = OrderedDict((str(i), f) for i, f in enumerate(features))
        return self.fpn(features)


def build_model(num_classes, pretrained=True):
    backbone = MobileNetV4FPN(pretrained)
    anchor_generator = AnchorGenerator(
        sizes=((16, 32), (32, 64), (64, 128)),
        aspect_ratios=((0.5, 1.0, 2.0),) * 3
    )
    roi_pool = MultiScaleRoIAlign(
        featmap_names=["0", "1", "2"],
        output_size=7,
        sampling_ratio=2
    )
    return FasterRCNN(
        backbone,
        num_classes=num_classes + 1,
        rpn_anchor_generator=anchor_generator,
        box_roi_pool=roi_pool,
        min_size=320,
        max_size=640,
        image_mean=[0.485, 0.456, 0.406],
        image_std=[0.229, 0.224, 0.225]
    )


def collate_fn(batch):
    return tuple(zip(*batch))


def check(classes):
    dataset = PPEData("train", len(classes))
    print("Device:", DEVICE)
    print("Classes:", list(enumerate(classes)))
    print("Train images:", len(dataset))
    try:
        val_dataset = PPEData("val", len(classes))
        print("Val images:", len(val_dataset))
    except ValueError:
        print("Val images: 0")

    image, target = dataset[0]
    print("Sample:", dataset.images[0].name)
    print("Image shape:", tuple(image.shape))
    print("Boxes:", tuple(target["boxes"].shape))
    print("Labels:", target["labels"].tolist())

    model = build_model(len(classes), pretrained=True).to(DEVICE)
    model.eval()
    with torch.inference_mode():
        features = model.backbone(
            torch.randn(1, 3, 320, 320, device=DEVICE)
        )
        for name, feat in features.items():
            print(f"FPN {name}: {tuple(feat.shape)}")
        output = model([image.to(DEVICE)])[0]
    print("Prediction shape:", tuple(output["boxes"].shape))


def train(args, classes):
    train_dataset = PPEData("train", len(classes))
    loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
        collate_fn=collate_fn
    )
    model = build_model(len(classes), pretrained=True).to(DEVICE)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    WEIGHTS.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        start = time.perf_counter()

        for images, targets in loader:
            images = [img.to(DEVICE) for img in images]
            targets = [
                {key: value.to(DEVICE) for key, value in t.items()}
                for t in targets
            ]
            losses = model(images, targets)
            loss = sum(losses.values())
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        avg_loss = total_loss / len(loader)
        elapsed = time.perf_counter() - start
        print(
            f"Epoch {epoch + 1}/{args.epochs} | "
            f"Loss: {avg_loss:.4f} | Time: {elapsed:.1f}s"
        )
        torch.save({
            "model": model.state_dict(),
            "classes": classes,
            "epoch": epoch + 1
        }, WEIGHTS)

    print("Saved:", WEIGHTS)


def predict(args, classes):
    checkpoint = torch.load(WEIGHTS, map_location="cpu", weights_only=True)
    if checkpoint["classes"] != classes:
        raise ValueError("체크포인트 클래스와 data.yaml이 다릅니다.")

    model = build_model(len(classes), pretrained=False)
    model.load_state_dict(checkpoint["model"])
    model = model.to(DEVICE).eval()

    image_path = Path(args.image)
    if not image_path.is_file():
        candidates = sorted((DATA_ROOT / "images" / "val").glob("*.jpg"))
        if not candidates:
            raise FileNotFoundError("검증 이미지가 없습니다.")
        image_path = candidates[0]
        print("선택된 이미지:", image_path)
    image = Image.open(image_path).convert("RGB")
    tensor = to_tensor(image).to(DEVICE)

    model.eval()
    times = []

    with torch.inference_mode():
        # GPU 준비를 위한 Warm-up
        for _ in range(10):
            model([tensor])

        if DEVICE.type == "cuda":
            torch.cuda.synchronize()

        # 30회 반복 추론
        for i in range(30):
            if DEVICE.type == "cuda":
                torch.cuda.synchronize()

            start = time.perf_counter()
            model([tensor])

            if DEVICE.type == "cuda":
                torch.cuda.synchronize()

            elapsed = time.perf_counter() - start
            times.append(elapsed)
            print(f"Inference {i + 1:02d}/30 | {elapsed * 1000:.1f} ms")

    print(f"Average latency: {statistics.mean(times) * 1000:.2f} ms")
    print(f"Average FPS: {1 / statistics.mean(times):.2f}")

    with torch.inference_mode():
        if DEVICE.type == "cuda":
            torch.cuda.synchronize()
        start = time.perf_counter()
        output = model([tensor])[0]
        if DEVICE.type == "cuda":
            torch.cuda.synchronize()
        elapsed = time.perf_counter() - start

    draw = ImageDraw.Draw(image)
    count = 0
    for box, label, score in zip(
    output["boxes"].cpu(),
    output["labels"].cpu(),
    output["scores"].cpu()
    ):
        if float(score) < args.conf:
            continue

        xyxy = [float(v) for v in box]
        x1, y1, x2, y2 = map(int, xyxy)
        name = classes[int(label) - 1]
        score_text = f"{name} {float(score):.2f}"

        worn_classes = {"helmet", "gloves", "vest", "boots", "goggles"}
        special_classes = {"Person", "forklift"}

        if name.startswith("no_"):
            box_color = "red"
            text_color = "white"
            fill_color = "red"
        elif name in worn_classes:
            box_color = "lime"
            text_color = "black"
            fill_color = None
        elif name in special_classes:
            box_color = "blue"
            text_color = "black"
            fill_color = None
        else:
            box_color = "lime"
            text_color = "black"
            fill_color = None

        draw.rectangle([x1, y1, x2, y2], outline=box_color, width=3)

        if fill_color is not None:
            text_w = len(score_text) * 8
            text_h = 18
            tx1 = x1
            ty1 = max(0, y1 - text_h - 2)
            tx2 = tx1 + text_w + 6
            ty2 = ty1 + text_h + 4
            draw.rectangle([tx1, ty1, tx2, ty2], fill=fill_color, outline=fill_color)
            draw.text((tx1 + 3, ty1 + 2), score_text, fill=text_color)
        else:
            draw.text((x1, max(0, y1 - 15)), score_text, fill=text_color)

        count += 1

    image.save(args.output)
    print(f"Detections: {count}")
    print(f"Latency: {elapsed * 1000:.1f} ms")
    print(f"FPS (single-image estimate): {1 / elapsed:.2f}")
    print("Saved:", args.output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=["check", "train", "predict"], default="check"
    )
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--lr", type=float, default=0.0001)
    parser.add_argument("--image", type=str, default="test.jpg")
    parser.add_argument("--output", type=str, default="result.jpg")
    parser.add_argument("--conf", type=float, default=0.5)
    args = parser.parse_args()

    classes = read_classes()
    if args.mode == "check":
        check(classes)
    elif args.mode == "train":
        train(args, classes)
    else:
        predict(args, classes)
>>>>>>> db913ff (add ppe, safety, sh17 dataset weights & py)
