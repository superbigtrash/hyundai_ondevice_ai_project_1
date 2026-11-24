# MobileNetV4 실험 기록 (사용 중단)

학습 모델로 YOLO를 쓰기로 하면서, 그 전에 시험한 MobileNetV4 + Faster R-CNN 코드와 가중치를 기록용으로 이 폴더에 옮겨 두었다. 지금 개발에는 쓰지 않는다. YOLO 비교 스크립트는 [`yolo_test/`](../../yolo_test/)에 있다.

## 파일

| 파일 | 내용 | 데이터셋 |
|---|---|---|
| `mbnv4_detect.py` | 학습·이미지 추론 | construction-ppe |
| `mbnv4_detect_usb.py` | USB 카메라 실시간 추론 추가 | construction-ppe |
| `mbnv4_safety.py` | 안전모·반사 조끼 모델 학습·추론 | safety-Helmet-Reflective-Jacket |
| `mbnv4_sh17.py` | 빈 파일 | SH17 |
| `weights/mobilenetv4_ppe.pth` | 가중치 (약 37MB) | construction-ppe |
| `weights/mobilenetv4_safety.pth` | 가중치 (약 37MB) | safety-Helmet-Reflective-Jacket |
| `weights/mobilenetv4_sh17.pth` | 가중치 (약 37MB) | SH17 |
| `result.jpg` | 추론 결과 예시 | |

## 옮길 당시 상태

코드는 옮기기만 하고 고치지 않았다. 다시 돌려 보려면 아래를 먼저 해결해야 한다.

- `mbnv4_detect.py`에 병합 충돌 표시(`<<<<<<<`, `=======`, `>>>>>>>`)가 남아 있어 그대로는 실행되지 않는다.
- `mbnv4_safety.py`에 `video()` 함수가 세 번 정의되어 있어 마지막 정의만 동작한다.
- 데이터 경로가 `C:\hyundai_project\...`로 고정되어 있다.
- 가중치 경로가 `weights/...` 상대 경로이므로 이 폴더에서 실행해야 한다.
