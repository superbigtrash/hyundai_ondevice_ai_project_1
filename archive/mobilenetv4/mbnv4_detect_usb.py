import argparse
import time
from collections import OrderedDict
from pathlib import Path

import cv2
import timm
import torch
import yaml
from PIL import Image, ImageDraw, ImageFont
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision.models.detection import FasterRCNN
from torchvision.models.detection.anchor_utils import AnchorGenerator
from torchvision.ops import FeaturePyramidNetwork, MultiScaleRoIAlign
from torchvision.transforms.functional import to_tensor

DATA_ROOT = Path(r'C:\hyundai_project\construction-ppe\construction-ppe')
WEIGHTS = Path('weights/mobilenetv4_ppe.pth')
MODEL_NAME = 'mobilenetv4_conv_small.e2400_r224_in1k'
DEVICE = torch.device("cpu")
WORN = {'helmet', 'gloves', 'vest', 'boots', 'goggles'}


def read_classes():
    with (DATA_ROOT / 'data.yaml').open(encoding='utf-8') as f:
        names = yaml.safe_load(f)['names']
    if isinstance(names, dict):
        names = {int(k): str(v) for k, v in names.items()}
        if sorted(names) != list(range(len(names))):
            raise ValueError('data.yaml 클래스 ID가 0부터 연속되어야 합니다.')
        return [names[i] for i in range(len(names))]
    return [str(n) for n in names]


class PPEData(Dataset):
    def __init__(self, split, class_count):
        self.img_dir = DATA_ROOT / 'images' / split
        self.label_dir = DATA_ROOT / 'labels' / split
        self.class_count = class_count
        self.images = sorted(p for p in self.img_dir.iterdir() if p.suffix.lower() in {'.jpg', '.jpeg', '.png'})
        if not self.images:
            raise ValueError(f'이미지가 없습니다: {self.img_dir}')

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        path = self.images[idx]
        image = Image.open(path).convert('RGB')
        w_img, h_img = image.size
        label_path = self.label_dir / (path.stem + '.txt')
        boxes, labels = [], []
        if label_path.exists():
            for line in label_path.read_text(encoding='utf-8').splitlines():
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) != 5:
                    raise ValueError(f'라벨 형식 오류: {label_path}: {line}')
                cls_f, xc, yc, w, h = map(float, parts)
                cls = int(cls_f)
                if cls != cls_f or not 0 <= cls < self.class_count:
                    raise ValueError(f'라벨 클래스 오류: {label_path}: {cls_f}')
                x1, y1 = max(0., (xc - w / 2) * w_img), max(0., (yc - h / 2) * h_img)
                x2, y2 = min(float(w_img), (xc + w / 2) * w_img), min(float(h_img), (yc + h / 2) * h_img)
                if x2 > x1 and y2 > y1:
                    boxes.append([x1, y1, x2, y2])
                    labels.append(cls + 1)
        return to_tensor(image), {'boxes': torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4), 'labels': torch.tensor(labels, dtype=torch.int64)}


class MobileNetV4FPN(nn.Module):
    def __init__(self, pretrained=True):
        super().__init__()
        self.encoder = timm.create_model(MODEL_NAME, pretrained=pretrained, features_only=True, out_indices=(2, 3, 4))
        self.fpn = FeaturePyramidNetwork(self.encoder.feature_info.channels(), out_channels=128)
        self.out_channels = 128

    def forward(self, x):
        feats = self.encoder(x)
        return self.fpn(OrderedDict((str(i), f) for i, f in enumerate(feats)))


def build_model(num_classes, pretrained=True):
    return FasterRCNN(
        MobileNetV4FPN(pretrained), num_classes=num_classes + 1,
        rpn_anchor_generator=AnchorGenerator(sizes=((16, 32), (32, 64), (64, 128)), aspect_ratios=((0.5, 1.0, 2.0),) * 3),
        box_roi_pool=MultiScaleRoIAlign(featmap_names=['0', '1', '2'], output_size=7, sampling_ratio=2),
        min_size=320, max_size=640,
        image_mean=[0.485, 0.456, 0.406], image_std=[0.229, 0.224, 0.225]
    )


def load_detector(classes):
    if not WEIGHTS.is_file():
        raise FileNotFoundError(f'학습 가중치가 없습니다: {WEIGHTS.resolve()}')
    ckpt = torch.load(WEIGHTS, map_location='cpu', weights_only=True)
    if ckpt['classes'] != classes:
        raise ValueError('체크포인트 클래스와 data.yaml이 다릅니다.')
    model = build_model(len(classes), pretrained=False)
    model.load_state_dict(ckpt['model'])
    return model.to(DEVICE).eval()


def draw_boxes(frame, output, classes, conf):
    h, w = frame.shape[:2]
    count = 0
    for box, label, score in zip(output['boxes'].cpu().tolist(), output['labels'].cpu().tolist(), output['scores'].cpu().tolist()):
        if score < conf:
            continue
        name = classes[label - 1]
        color = (0, 0, 255) if name.startswith('no_') else (0, 220, 0) if name in WORN else (255, 170, 0)
        fg = (255, 255, 255) if name.startswith('no_') else (0, 0, 0)
        x1, y1, x2, y2 = [int(round(z)) for z in box]
        x1, x2 = max(0, min(w - 1, x1)), max(0, min(w - 1, x2))
        y1, y2 = max(0, min(h - 1, y1)), max(0, min(h - 1, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        caption = f'{name} {score:.2f}'
        font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1
        (tw, th), base = cv2.getTextSize(caption, font, scale, thick)
        tx = max(0, min(x1, w - tw - 8))
        ty = y1 - 4 if y1 >= th + 10 else min(h - 3, y1 + th + 10)
        top, bottom = max(0, ty - th - 5), min(h - 1, ty + base + 3)
        cv2.rectangle(frame, (tx, top), (min(w - 1, tx + tw + 8), bottom), color, -1)
        cv2.putText(frame, caption, (tx + 4, max(th + 1, ty - 2)), font, scale, fg, thick, cv2.LINE_AA)
        count += 1
    return count


def check(classes):
    ds = PPEData('train', len(classes))
    print('Device:', DEVICE, '| Classes:', list(enumerate(classes)))
    print('Train:', len(ds), '| Val:', len(PPEData('val', len(classes))))
    model = build_model(len(classes), pretrained=True).to(DEVICE).eval()
    with torch.inference_mode():
        out = model([ds[0][0].to(DEVICE)])[0]
    print('Prediction boxes:', tuple(out['boxes'].shape))


def train(args, classes):
    ds = PPEData('train', len(classes))
    dl = DataLoader(ds, batch_size=args.batch_size, shuffle=True, num_workers=0, collate_fn=lambda batch: tuple(zip(*batch)))
    model = build_model(len(classes), pretrained=True).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    WEIGHTS.parent.mkdir(parents=True, exist_ok=True)
    for epoch in range(args.epochs):
        model.train()
        total = 0.
        start = time.perf_counter()
        for imgs, targets in dl:
            imgs = [img.to(DEVICE) for img in imgs]
            targets = [{k: v.to(DEVICE) for k, v in t.items()} for t in targets]
            losses = model(imgs, targets)
            loss = sum(losses.values())
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item()
        print(f'Epoch {epoch+1}/{args.epochs} | Loss {total/len(dl):.4f} | Time {time.perf_counter()-start:.1f}s', flush=True)
        torch.save({'model': model.state_dict(), 'classes': classes, 'epoch': epoch + 1}, WEIGHTS)


def predict(args, classes):
    model = load_detector(classes)
    path = Path(args.image)
    if not path.is_file():
        candidates = sorted((DATA_ROOT / 'images' / 'val').glob('*.jpg'))
        if not candidates:
            raise FileNotFoundError('검증 이미지가 없습니다.')
        path = candidates[0]
        print('선택된 이미지:', path)
    image = Image.open(path).convert('RGB')
    tensor = to_tensor(image).to(DEVICE)
    with torch.inference_mode():
        for _ in range(10):
            model([tensor])
        if DEVICE.type == 'cuda':
            torch.cuda.synchronize()
        durations = []
        for i in range(30):
            if DEVICE.type == 'cuda':
                torch.cuda.synchronize()
            st = time.perf_counter()
            out = model([tensor])[0]
            if DEVICE.type == 'cuda':
                torch.cuda.synchronize()
            duration = time.perf_counter() - st
            durations.append(duration)
            print(f'Inference {i+1:02d}/30 | {duration*1000:.1f} ms')
    import numpy as np
    frame = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR).copy()
    count = draw_boxes(frame, out, classes, args.conf)
    cv2.imwrite(args.output, frame)
    avg = sum(durations) / len(durations)
    print(f'Average latency: {avg*1000:.2f} ms | Average FPS: {1/avg:.2f}')
    print(f'Detections: {count} | Saved: {args.output}')


def video(args, classes):
    model = load_detector(classes)
    source = int(args.source) if args.source.isdecimal() else args.source
    cap = cv2.VideoCapture(source, cv2.CAP_DSHOW) if isinstance(source, int) else cv2.VideoCapture(source)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f'카메라/영상을 열 수 없습니다: {args.source} (다른 앱의 카메라 점유 여부도 확인하세요)')
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    print('Source:', args.source, '| Capture:', int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), 'x', int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    print('Q 또는 ESC: 종료', flush=True)
    fps_smooth = None
    try:
        while True:
            t0 = time.perf_counter()
            ok, frame = cap.read()
            if not ok:
                print('프레임 수집 실패/동영상 종료')
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            tensor = to_tensor(Image.fromarray(rgb)).to(DEVICE)
            with torch.inference_mode():
                out = model([tensor])[0]
            count = draw_boxes(frame, out, classes, args.conf)
            if DEVICE.type == 'cuda':
                torch.cuda.synchronize()
            elapsed = time.perf_counter() - t0
            current = 1 / max(elapsed, 1e-6)
            fps_smooth = current if fps_smooth is None else 0.85 * fps_smooth + 0.15 * current
            cv2.rectangle(frame, (8, 8), (310, 50), (0, 0, 0), -1)
            cv2.putText(frame, f'FPS {fps_smooth:.1f} | Objects {count}', (16, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow('MobileNetV4 PPE - USB Camera', frame)
            if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['check', 'train', 'predict', 'video'], default='check')
    parser.add_argument('--epochs', type=int, default=20)
    parser.add_argument('--batch-size', type=int, default=2)
    parser.add_argument('--lr', type=float, default=0.0001)
    parser.add_argument('--image', type=str, default='test.jpg')
    parser.add_argument('--output', type=str, default='result.jpg')
    parser.add_argument('--conf', type=float, default=0.5)
    parser.add_argument('--source', type=str, default='0')
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    args = parser.parse_args()
    DEVICE = torch.device(args.device)
    classes = read_classes()
    print('Device:', DEVICE)
    if args.mode == 'check':
        check(classes)
    elif args.mode == 'train':
        train(args, classes)
    elif args.mode == 'predict':
        predict(args, classes)
    else:
        video(args, classes)

## 명령어 python mbnv4_detect_usb.py --mode video --source 0 --device cpu --conf 0.7