# 통신 (MQTT)
 
노트북 1대와 라즈베리파이 3대가 **MQTT**로 메시지를 주고받는 기본 통신 코드입니다.
지금은 센서·AI 대신 **키보드 입력으로 상황을 흉내 내서** 통신만 확인하는 단계예요.
 
## 구성
 
| 기기 | 역할 | 호스트명 | IP (예시) | 언어 | 파일 |
|---|---|---|---|---|---|
| 노트북 | 브로커 + 중앙 서버 | - | 192.168.20.123 | Python | `server/server.py` (콘솔)<br>`server/server_gui.py` (대시보드) |
| **1번 파이** | ③ 설비 제어부 | JGH1628 | 192.168.20.26 | C | `equipment/pi_equipment.c` |
| **2번 파이** | ② 현장 감시부 | rpi-jsm6049 | 192.168.20.45 | Python | `site/pi_site.py` |
| **3번 파이** | ① 입구 제어부 | rpi-kks2021 | 192.168.20.168 | Python | `entrance/pi_entrance.py` (키보드 테스트)<br>`entrance/pi_entrance_yolo.py` (YOLO 판정) |
 
> IP는 공유기가 자동으로 나눠주기 때문에 바뀔 수 있습니다. 접속이 안 되면 `ipconfig`(노트북)와 `hostname -I`(파이)로 먼저 확인하세요.
 
AI·카메라가 들어가는 파이는 Python, 단순 제어만 하는 설비 파이는 C로 작성했습니다.
 
## 토픽
 
모든 토픽은 `safety/파트/내용` 규칙을 따릅니다.
 
| 토픽 | 보내는 쪽 → 받는 쪽 | 내용 예시 | 의미 |
|---|---|---|---|
| `safety/entrance/result` | 입구 → 서버 | `{"helmet": true, "vest": true, "persons": 1, "detections": [...]}` | 보호구 판정 결과 (YOLO 버전은 사람 수와 박스 목록 포함) |
| `safety/entrance/door` | 입구 → 서버 | `{"door": "open"}` | 문 상태 (`open` / `closed`) |
| `safety/site/ppe` | 현장 → 서버 | `{"helmet": false, "vest": true}` | 작업자 착용 감시 결과 |
| `safety/site/thermal` | 현장 → 서버 | `{"max_temp": 65.0}` | 열화상 최고 온도 (°C) |
| `safety/site/alarm` | 서버 → 현장 | `{"alarm": "on"}` | 현장 경보 켜기/끄기 |
| `safety/equipment/cmd` | 서버 → 설비 | `{"cmd": "STOP"}` | 설비 차단(`STOP`) / 해제(`RUN`) |
| `safety/equipment/status` | 설비 → 서버 | `{"motor": "stopped"}` | 설비 상태 (`stopped` / `running`) |
 
```mermaid
flowchart LR
    E["① 입구<br>3번 파이"] -- "entrance/result<br>entrance/door" --> B(("브로커"))
    S["② 현장<br>2번 파이"] -- "site/ppe<br>site/thermal" --> B
    Q["③ 설비<br>1번 파이"] -- "equipment/status" --> B
    B -- "safety/#" --> SV["중앙 서버"]
    SV -- "site/alarm" --> B
    SV -- "equipment/cmd" --> B
    B -- "site/alarm" --> S
    B -- "equipment/cmd" --> Q
```
 
| 기기 | 구독하는 토픽 |
|---|---|
| 중앙 서버 | `safety/#` (전체) |
| 현장 파이 | `safety/site/alarm` |
| 설비 파이 | `safety/equipment/cmd` |
| 입구 파이 | 없음 (보내기만 함) |
 
현재 설정: 모든 메시지 **QoS 0**, **retain 없음**, keepalive **60초**, clean session.
 
## 설치
 
### 노트북 (Windows)
 
1. [mosquitto.org/download](https://mosquitto.org/download/)에서 Windows 64비트 설치 파일을 받아 설치합니다. 설치 중 **Service 체크는 해제**하세요.
2. 관리자 권한 메모장으로 `C:\Program Files\mosquitto\mosquitto.conf`를 열고, 이 폴더의 [`mosquitto.conf`](mosquitto.conf) 내용(두 줄)을 맨 아래에 추가합니다.
3. 관리자 PowerShell에서 방화벽 1883 포트를 엽니다.
```
New-NetFirewallRule -DisplayName "MQTT 1883" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow
```
4. 파이썬 라이브러리를 설치합니다.
```
pip install -r requirements.txt
```
 
### 2번 파이(현장) / 3번 파이(입구) — Python
 
라즈베리파이 OS는 시스템 보호를 위해 `pip install`을 막아두므로 가상환경을 사용합니다.
`--system-site-packages`는 나중에 카메라 라이브러리(picamera2)를 같이 쓰기 위한 옵션입니다.
 
```
sudo apt update
sudo apt install mosquitto-clients
python3 -m venv --system-site-packages ~/venv
source ~/venv/bin/activate
pip install paho-mqtt
```
 
### 1번 파이(설비) — C
 
```
sudo apt update
sudo apt install build-essential libmosquitto-dev mosquitto-clients
gcc pi_equipment.c -o pi_equipment -lmosquitto
```
 
C 코드의 `#define BROKER` 주소를 바꾸면 **반드시 다시 컴파일**해야 합니다.
 
## 실행 순서
 
받는 쪽부터 켜야 메시지를 놓치지 않습니다.
 
| 순서 | 위치 | 명령 |
|---|---|---|
| 1 | 노트북 (브로커) | `cd "C:\Program Files\mosquitto"` → `.\mosquitto -c mosquitto.conf -v` |
| 2 | 노트북 (서버) | `python server.py` 또는 `python server_gui.py` (둘 중 **하나만**) |
| 3 | 1번 파이 (설비) | `./pi_equipment` |
| 4 | 2번 파이 (현장) | `source ~/venv/bin/activate` → `python pi_site.py` |
| 5 | 3번 파이 (입구) | `source ~/venv/bin/activate` → `python pi_entrance.py` |
 
PowerShell에서는 현재 폴더의 프로그램 앞에 `.\`를 붙여야 실행됩니다.
 
## 입구 YOLO 판정 (pi_entrance_yolo.py)
 
카메라 사진을 `best_int8.onnx`(YOLO26n, INT8 양자화, 입력 416×416)로 판정해서 결과를 MQTT로 보냅니다.
 
| 항목 | 내용 |
|---|---|
| 클래스 | `helmet`, `no_helmet`, `vest`, `no_vest`, `person` |
| 판정 | 화면에 `helmet`이 있고 `no_helmet`이 없으면 안전모 착용 (안전복도 같은 방식) |
| 확정 | 같은 결과가 **5장 연속**이면 확정해서 **한 번만** 전송 |
| 사람 없음 | 보내지 않고 초기화 → 다음 사람이 오면 다시 판정 |
| 속도 | 5초마다 FPS를 화면에 출력 |
 
설치 (3번 파이, 가상환경 켠 상태):
 
```
sudo apt install python3-picamera2 python3-opencv
pip install onnxruntime
```
 
`best_int8.onnx`를 코드와 같은 폴더에 두고 `python pi_entrance_yolo.py`로 실행합니다.
키보드 테스트 버전(`pi_entrance.py`)과 이름(`client_id`)이 같으니 **둘 중 하나만** 실행하세요.
 
## 대시보드 (server_gui.py)
 
`server.py`와 같은 일을 **CustomTkinter**(다크 모드, 둥근 카드 디자인) 창으로 보여주는 버전입니다.
`pip install -r requirements.txt`로 `customtkinter`도 같이 설치됩니다.
 
| 영역 | 내용 |
|---|---|
| 맨 위 | 브로커 연결 상태 (초록: 연결 / 빨강: 끊김) |
| ① 입구 | 보호구 판정 결과, 출입문 상태 |
| ② 현장 | 착용 감시, 최고 온도(50°C 이상 빨강), 경보 상태, 경보 켜기·끄기 버튼 |
| ③ 설비 | 모터 상태, 설비 차단·해제 버튼 |
| 출입 통계 | 통과, 거부, 통과율, 안전모·안전복 미착용 횟수, 초기화 (날짜가 바뀌면 자동 초기화) |
| 메시지 기록 | 시간과 함께 송신·수신 메시지 표시 |
 
- 두 파일 모두 `client_id="server"`를 쓰기 때문에 **동시에 실행하면 서로 접속을 끊습니다.** 하나만 실행하세요.
- 출입 통계는 프로그램을 끄면 0으로 돌아갑니다.
- MQTT 콜백은 별도 스레드에서 실행되므로, 받은 메시지를 `queue`에 넣고 화면 쪽에서 `root.after()`로 0.1초마다 꺼내 처리합니다.
## 통신 테스트
 
| 테스트 | 어디서 | 입력 | 확인할 곳 |
|---|---|---|---|
| 입구 → 서버 | 입구 파이 | `1`~`4` | 서버: `[수신] safety/entrance/...` |
| 현장 → 서버 | 현장 파이 | `1`~`4` | 서버: `[수신] safety/site/...` |
| 서버 → 현장 | 서버 | `3`, `4` | 현장 파이: `[수신] safety/site/alarm` |
| 서버 → 설비 → 서버 | 서버 | `1`, `2` | 설비 파이 `[수신]`·`[송신]` → 서버 `[수신] safety/equipment/status` |
 
브로커 창(`-v`)에 `as server`, `as pi_entrance`, `as pi_site`, `as pi_equipment` 4개의 접속 기록이 있어야 합니다.
 
브로커 없이 접속만 확인하고 싶을 때는 테스트 도구를 씁니다.
 
```
mosquitto_sub -h 192.168.20.123 -t "safety/#" -v -d
```
 
`received CONNACK (0)`이 나오면 접속 성공입니다.
 
## 문제 해결
 
| 증상 | 원인 | 해결 |
|---|---|---|
| PowerShell에서 `mosquitto`를 찾을 수 없음 | 현재 폴더 프로그램 실행 제한 | 앞에 `.\` 붙이기 |
| `연결을 거부했으므로 연결하지 못했습니다` | 브로커가 꺼져 있음 | 브로커 창 확인 후 다시 실행 |
| 파이 ping 결과 `Destination Host Unreachable` | 노트북 IP가 바뀜 | `ipconfig`로 확인 후 코드 주소 수정 |
| 파이 ping에 아무 응답 없음 | Windows는 ping에 응답하지 않음 (정상) | ping 대신 `mosquitto_sub`으로 확인 |
| 파이 `mosquitto_sub`이 멈춰 있고 브로커에 접속 기록 없음 | 방화벽이 1883 차단 | Windows 방화벽 규칙 추가, **백신(Avast 등) 방화벽** 확인 |
| `externally-managed-environment` | 파이 OS가 pip 설치를 막음 | 가상환경(venv) 사용 |
| `IndentationError` | nano 붙여넣기 중 들여쓰기 깨짐 | 함수 안 4칸, if 안 8칸으로 맞추기 |
 
> **참고:** Windows 보안 → 방화벽 화면에 "다른 공급자를 사용하고 있기 때문에 Microsoft Defender 방화벽이 활성화되어 있지 않습니다"가 보이면, 백신 프로그램이 방화벽을 관리하는 상태입니다. 이 경우 Windows 방화벽 규칙은 적용되지 않으니 백신 설정에서 1883 포트를 허용해야 합니다.
 