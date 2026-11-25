import torch
from ultralytics import YOLO
import sys
import time
import json
from pathlib import Path
from datetime import datetime
import cv2
import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFrame
CAMERA_INDEX = 0
WEIGHTS = r'C:\hyundai_project\project_1\runs\helmet_vest\yolo26n_416\weights\best.pt'
DEVICE = 'cpu'
IMG_SIZE = 416
CONF = 0.20
INSPECTION_SECONDS = 3.0
FAIL_DISPLAY_SECONDS = 2.0
MIN_SAMPLES = 3
PASS_RATIO = 0.80
SHOW_BOXES = False
GUIDE_MIN_COVERAGE = 0.85
PERSON_MIN_INSIDE = 0.55
POSITION_FRAMES = 3
PPE_CONF = 0.50
HELMET_GUIDE_INSIDE = 0.85
VEST_GUIDE_INSIDE = 0.85
VEST_CORE_COVERAGE = 0.75
# Fixed chest reference inside the white guide (x1,y1,x2,y2).
VEST_CORE = (155, 218, 285, 365)
HEAD_BOTTOM = 150
SAVE_CONFIG_JSON = True
SAVE_RESULTS_JSON = True
CONFIG_JSON = Path(__file__).resolve().parent / 'ppe_config.json'
RESULTS_JSON = Path(__file__).resolve().parent / 'ppe_results.json'

def write_json(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4, allow_nan=False)
    temp.replace(path)

def save_config():
    keys = ('CAMERA_INDEX', 'WEIGHTS', 'DEVICE', 'IMG_SIZE', 'CONF',
            'INSPECTION_SECONDS', 'FAIL_DISPLAY_SECONDS', 'MIN_SAMPLES',
            'PASS_RATIO', 'SHOW_BOXES', 'GUIDE_MIN_COVERAGE', 'PERSON_MIN_INSIDE',
            'POSITION_FRAMES', 'PPE_CONF', 'HELMET_GUIDE_INSIDE',
            'VEST_GUIDE_INSIDE', 'VEST_CORE_COVERAGE', 'VEST_CORE', 'HEAD_BOTTOM')
    write_json(CONFIG_JSON, {key: globals()[key] for key in keys})
    print('Config saved:', CONFIG_JSON, flush=True)

def save_result(pair):
    record = {
        'timestamp': datetime.now().astimezone().isoformat(timespec='seconds'),
        'result': 'SUCCESS' if pair == ('WORN', 'WORN') else 'FAILED',
        'helmet': pair[0], 'vest': pair[1]
    }
    records = []
    if RESULTS_JSON.exists():
        with RESULTS_JSON.open(encoding='utf-8') as f:
            records = json.load(f)
        if not isinstance(records, list):
            raise ValueError('Result JSON must contain a list')
    records.append(record)
    write_json(RESULTS_JSON, records)
    print('Result saved:', RESULTS_JSON, flush=True)

if SAVE_CONFIG_JSON:
    try:
        save_config()
    except (OSError, ValueError) as exc:
        print('Config save error:', exc, flush=True)
model = YOLO(WEIGHTS)
print('Classes:', model.names)
def normalize(name):
    return name.lower().replace('-', '_').replace(' ', '_')
PERSON = {'person', 'people'}
HELMET = {'helmet', 'safety_helmet', 'hardhat', 'hard_hat'}
VEST = {'vest', 'safety_vest', 'reflective_jacket', 'safety_jacket'}
NO_HELMET = {'no_helmet', 'no_hardhat', 'no_hard_hat', 'no_safety_helmet'}
NO_VEST = {'no_vest', 'no_safety_vest', 'no_reflective_jacket'}
class Kiosk(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('PPE Safety Inspection')
        self.setFixedSize(800, 480)
        self.setStyleSheet('QWidget{background:#101820;color:#f1f5f9;font-family:Segoe UI,Malgun Gothic;} QFrame{background:#202d38;border-radius:8px;} QLabel{background:transparent;} QPushButton{background:#334155;border:0;border-radius:8px;font-size:17px;font-weight:bold;padding:12px;} QPushButton:hover{background:#475569;}')
        root = QVBoxLayout(self)
        root.setContentsMargins(14,10,14,12)
        root.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel('PPE SAFETY INSPECTION')
        title.setStyleSheet('font-size:21px;font-weight:bold;')
        self.camera_status = QLabel('CAMERA ...')
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.camera_status)
        root.addLayout(header)
        body = QHBoxLayout()
        body.setSpacing(12)
        self.video = QLabel('Camera unavailable')
        self.video.setFixedSize(440,420)
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setStyleSheet('background:#35414b;border-radius:8px;')
        body.addWidget(self.video)
        right = QVBoxLayout()
        self.status = self.panel(right,'INSPECTION STATUS')
        self.helmet = self.panel(right,'SAFETY HELMET')
        self.vest = self.panel(right,'SAFETY VEST')
        self.message = QLabel()
        self.message.setAlignment(Qt.AlignCenter)
        self.message.setWordWrap(True)
        right.addWidget(self.message)
        reset = QPushButton('RESET / 재검사')
        reset.clicked.connect(self.reset)
        right.addWidget(reset)
        body.addLayout(right,1)
        root.addLayout(body)
        self.mask = np.zeros((420,440),np.uint8)
        self.outline = np.array([(220,34),(190,40),(169,58),(158,85),(158,116),(166,144),(184,162),(184,181),(137,194),(104,220),(88,260),(77,409),(363,409),(352,260),(336,220),(303,194),(256,181),(256,162),(274,144),(282,116),(282,85),(271,58),(250,40)],np.int32)
        cv2.fillPoly(self.mask,[self.outline],255)
        self.head_mask = self.mask.copy()
        self.head_mask[HEAD_BOTTOM:,:] = 0
        self.torso_mask = self.mask.copy()
        self.torso_mask[:190,:] = 0
        self.cap = cv2.VideoCapture(CAMERA_INDEX,cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
        self.debug_tick = 0
        self.reset()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(33)
    def panel(self,parent,title):
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12,8,12,8)
        label = QLabel(title)
        label.setStyleSheet('font-size:14px;color:#b7c6d3;font-weight:bold;')
        result = QLabel()
        layout.addWidget(label)
        layout.addWidget(result)
        parent.addWidget(frame)
        return result
    def paint_label(self,label,text,color,size=18):
        label.setText(text)
        label.setStyleSheet(f'font-size:{size}px;color:{color};font-weight:bold;')
    def reset(self):
        self.position_count = 0
        self.previous = None
        self.target_box = None
        self.count = 0
        self.started_at = None
        self.samples = []
        self.final_pair = None
        self.failed_at = None
        self.paint_label(self.status,'WAITING','#facc15',32)
        self.paint_label(self.helmet,'NOT CHECKED','#94a3b8')
        self.paint_label(self.vest,'NOT CHECKED','#94a3b8')
        self.message.setText('상체를 가이드에 맞춰주세요')
    def update_frame(self):
        ok,frame = self.cap.read()
        if not ok:
            self.reset()
            self.camera_status.setText('CAMERA OFF')
            self.video.setText('Camera unavailable')
            return
        self.camera_status.setText('CAMERA ON')
        self.camera_status.setStyleSheet('color:#4ade80;')
        frame = cv2.flip(frame,1)
        h,w = frame.shape[:2]
        scale = max(440/w,420/h)
        frame = cv2.resize(frame,(int(np.ceil(w*scale)),int(np.ceil(h*scale))))
        y,x = (frame.shape[0]-420)//2,(frame.shape[1]-440)//2
        frame = frame[y:y+420,x:x+440].copy()
        result = model.predict(frame,imgsz=IMG_SIZE,conf=CONF,device=DEVICE,verbose=False)[0]
        detections = []
        for box in result.boxes:
            name = normalize(result.names[int(box.cls.item())])
            coords = tuple(map(int,box.xyxy[0].tolist()))
            detections.append((name,coords,float(box.conf.item())))
        dark = (frame.astype(np.float32)*0.35).astype(np.uint8)
        frame = np.where(self.mask[:,:,None]>0,frame,dark)
        cv2.polylines(frame,[self.outline],True,(235,235,235),2,cv2.LINE_AA)
        people = [d for d in detections if d[0] in PERSON]
        def area(box):
            x1,y1,x2,y2 = box
            return max(0,x2-x1)*max(0,y2-y1)
        def intersection(a,b):
            return area((max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3])))
        self.debug_tick += 1
        if not people:
            self.reset()
            self.message.setText('사람이 탐지되지 않았습니다' if any(normalize(n) in PERSON for n in model.names.values()) else '모델에 person 클래스가 필요합니다')
        else:
            target = max(people,key=lambda d: area(d[1]))
            person_box = target[1]
            px1,py1,px2,py2 = person_box
            if self.target_box is not None:
                overlap = intersection(self.target_box,person_box)
                union = area(self.target_box)+area(person_box)-overlap
                if overlap/max(1,union)<0.5:
                    self.reset()
            self.target_box = person_box
            # Rectangle approximation of the person silhouette, using the existing guide mask.
            xlo,ylo = max(0,px1),max(0,py1)
            xhi,yhi = min(440,px2),min(420,py2)
            overlap_pixels = cv2.countNonZero(self.mask[ylo:yhi,xlo:xhi]) if xhi>xlo and yhi>ylo else 0
            guide_coverage = overlap_pixels/max(1,cv2.countNonZero(self.mask))
            person_inside = overlap_pixels/max(1,area(person_box))
            aligned = guide_coverage >= GUIDE_MIN_COVERAGE and person_inside >= PERSON_MIN_INSIDE
            self.position_count = self.position_count+1 if aligned else 0
            ready = self.position_count >= POSITION_FRAMES
            outline_color = (235,235,235)
            cv2.polylines(frame,[self.outline],True,outline_color,2,cv2.LINE_AA)
            if SHOW_BOXES:
                cv2.rectangle(frame,(px1,py1),(px2,py2),(255,180,0),2)
                cv2.putText(frame,f'Person {target[2]:.2f}',(px1,max(15,py1-5)),cv2.FONT_HERSHEY_SIMPLEX,0.45,(255,180,0),2,cv2.LINE_AA)
            if not ready:
                self.previous = None
                self.count = 0
                self.started_at = None
                self.samples = []
                self.final_pair = None
                self.failed_at = None
                self.paint_label(self.status,'POSITIONING','#facc15',25)
                self.paint_label(self.helmet,'NOT CHECKED','#94a3b8')
                self.paint_label(self.vest,'NOT CHECKED','#94a3b8')
                self.message.setText('상체를 가이드에 맞춰주세요')
                if self.debug_tick % 15 == 1:
                    print(f'Guide={guide_coverage:.2f} Inside={person_inside:.2f} Aligned={aligned}',flush=True)
            else:
                ph = max(1,py2-py1)
                found = set()
                def mask_fraction(mask, box):
                    a,b,c,d = box
                    a,b,c,d = max(0,a),max(0,b),min(440,c),min(420,d)
                    return cv2.countNonZero(mask[b:d,a:c])/max(1,area(box)) if c>a and d>b else 0.0
                candidates = {"helmet": [], "vest": []}
                for name,(x1,y1,x2,y2),score in detections:
                    if name not in HELMET|NO_HELMET|VEST|NO_VEST:
                        continue
                    box = (x1,y1,x2,y2)
                    cx,cy = (x1+x2)//2,(y1+y2)//2
                    if not (px1<=cx<=px2 and py1<=cy<=py2):
                        continue
                    if intersection(box,person_box)/max(1,area(box))<0.5:
                        continue
                    # Ignore equipment better associated with another person.
                    coverage = intersection(box,person_box)/max(1,area(box))
                    if any(intersection(box,d[1])/max(1,area(box))>coverage for d in people if d is not target):
                        continue
                    if name in HELMET|NO_HELMET and cy>py1+ph*0.45:
                        continue
                    if name in VEST|NO_VEST and cy<py1+ph*0.2:
                        continue
                    group = "helmet" if name in HELMET|NO_HELMET else "vest"
                    candidates[group].append((name, box, score))
                for group in candidates.values():
                    if not group:
                        continue
                    name, (x1,y1,x2,y2), score = max(group, key=lambda d: (area(d[1]), d[2]))
                    box = (x1,y1,x2,y2)
                    is_head = name in HELMET|NO_HELMET
                    inside = mask_fraction(self.head_mask if is_head else self.torso_mask, box)
                    core = intersection(box,VEST_CORE)/area(VEST_CORE) if not is_head else 1.0
                    cx,cy = (x1+x2)//2,(y1+y2)//2
                    center_ok = 0<=cx<440 and 0<=cy<420 and bool((self.head_mask if is_head else self.torso_mask)[cy,cx])
                    valid = score >= PPE_CONF and center_ok and inside >= (HELMET_GUIDE_INSIDE if is_head else VEST_GUIDE_INSIDE)
                    if name in VEST:
                        valid = valid and core >= VEST_CORE_COVERAGE
                    if valid:
                        found.add(name)
                    color = ((0,0,255) if name in NO_HELMET|NO_VEST else (0,255,0)) if valid else (0,165,255)
                    if self.debug_tick % 15 == 1:
                        print(f'{name}: conf={score:.2f} guide={inside:.2f} chest={core:.2f} valid={valid}',flush=True)
                    if SHOW_BOXES:
                        cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)
                        cv2.putText(frame,f'{name} {score:.2f}' + ('' if valid else ' RECHECK'),(x1,max(15,y1-5)),cv2.FONT_HERSHEY_SIMPLEX,0.45,color,2,cv2.LINE_AA)
                if self.debug_tick % 15 == 1:
                    print('People:',len(people),'| Target area:',area(person_box),'| Target PPE:',sorted(found),flush=True)
                def state(yes,no):
                    positive,negative = bool(found&yes),bool(found&no)
                    return 'WORN' if positive and not negative else 'NOT WORN' if negative and not positive else 'UNKNOWN'
                pair = (state(HELMET,NO_HELMET),state(VEST,NO_VEST))
                now = time.monotonic()
                if self.started_at is None:
                    self.started_at = now
                elapsed = now - self.started_at
                if self.final_pair is None:
                    self.samples.append(pair)
                    if elapsed >= INSPECTION_SECONDS and len(self.samples) >= MIN_SAMPLES:
                        self.final_pair = tuple(
                            'WORN' if sum(p[i] == 'WORN' for p in self.samples)/len(self.samples) >= PASS_RATIO
                            and not any(p[i] == 'NOT WORN' for p in self.samples)
                            else 'NOT CONFIRMED' for i in range(2))
                        print('Inspection:', self.final_pair, 'samples:', len(self.samples), flush=True)
                        if SAVE_RESULTS_JSON:
                            try:
                                save_result(self.final_pair)
                            except (OSError, ValueError) as exc:
                                print('Result save error:', exc, flush=True)
                if self.final_pair is None:
                    self.paint_label(self.status,'CHECKING','#facc15',28)
                    self.paint_label(self.helmet,'CHECKING','#94a3b8')
                    self.paint_label(self.vest,'CHECKING','#94a3b8')
                    self.message.setText(f'검사 중... {min(elapsed, INSPECTION_SECONDS):.1f} / {INSPECTION_SECONDS:.0f}초')
                else:
                    passed = self.final_pair == ('WORN','WORN')
                    if not passed and self.failed_at is None:
                        self.failed_at = now
                    if not passed and now - self.failed_at >= FAIL_DISPLAY_SECONDS:
                        self.reset()
                        self.paint_label(self.status,'POSITIONING','#facc15',25)
                        self.message.setText('상체를 가이드에 맞춰주세요')
                    else:
                        for label,value in zip((self.helmet,self.vest),self.final_pair):
                            self.paint_label(label,value,'#4ade80' if value=='WORN' else '#f87171')
                        self.paint_label(self.status,'SUCCESS' if passed else 'FAILED','#4ade80' if passed else '#f87171',32)
                        self.message.setText('안전장비 착용 완료' if passed else '안전장비 착용을 확인해주세요')
                        cv2.polylines(frame,[self.outline],True,(0,255,0) if passed else (0,0,255),2,cv2.LINE_AA)
        rgb = cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
        image = QImage(rgb.data,440,420,rgb.strides[0],QImage.Format_RGB888).copy()
        self.video.setPixmap(QPixmap.fromImage(image))
    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
    def closeEvent(self,event):
        self.timer.stop()
        self.cap.release()
        super().closeEvent(event)
if __name__=='__main__':
    app = QApplication(sys.argv)
    window = Kiosk()
    window.show()
    sys.exit(app.exec_())
