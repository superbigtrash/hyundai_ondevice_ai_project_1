from ultralytics import YOLO

WEIGHTS = r"C:\hyundai_project\project_1\runs\helmet_vest\yolo26n_416\weights\best.pt"
DATA = r"C:\hyundai_project\construction-ppe\construction-ppe-5class\data.yaml"

model = YOLO(WEIGHTS)

# ONNX FP32 변환
model.export(
    format="onnx",
    imgsz=416,
    simplify=True,
    dynamic=False,
    device="cpu",
    quantize=32
)

# ONNX INT8 Static Quantization
model.export(
    format="onnx",
    imgsz=416,
    simplify=True,
    dynamic=False,
    device="cpu",
    quantize=8,
    data=DATA,
    fraction=1.0
)