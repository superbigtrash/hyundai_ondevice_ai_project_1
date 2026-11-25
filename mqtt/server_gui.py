# ============================================
# 중앙 서버 (노트북) - 대시보드 (CustomTkinter)
# - server.py와 같은 일을 하지만, 결과를 창에 보여준다
# - 받은 데이터로 입구/현장/설비 상태를 표시한다
# - 버튼으로 설비 차단/해제, 현장 경보를 보낸다
# - 입구 판정 결과로 출입 통계를 센다
# 설치: pip install customtkinter paho-mqtt
# ============================================
import json
import queue
from datetime import datetime

import customtkinter as ctk
import paho.mqtt.client as mqtt

BROKER = "localhost"
HOT_TEMP = 50.0  # 이 온도(°C) 이상이면 빨간색으로 표시

# 색상
GREEN = "#16a34a"
RED = "#dc2626"
GRAY = "#475569"
BLUE = "#2563eb"
CARD = "#1e293b"   # 카드 배경
BG = "#0f172a"     # 창 배경
SUB = "#94a3b8"    # 흐린 글자

ctk.set_appearance_mode("dark")

# MQTT 콜백은 다른 스레드에서 실행되기 때문에 화면을 직접 바꾸면 안 된다.
# 그래서 받은 메시지를 이 "우체통"에 넣어두고, 화면 쪽에서 꺼내 쓴다.
inbox = queue.Queue()

# 출입 통계 (프로그램을 끄면 0으로 돌아간다)
stats = {"date": datetime.now().date(), "pass": 0, "deny": 0, "no_helmet": 0, "no_vest": 0}


# ---------------- MQTT (뒤에서 도는 부분) ----------------

def on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe("safety/#")
    inbox.put(("__connected__", str(reason_code)))


def on_disconnect(client, userdata, flags, reason_code, properties):
    inbox.put(("__disconnected__", str(reason_code)))


def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        data = msg.payload.decode(errors="replace")  # JSON이 아니면 글자 그대로
    inbox.put((msg.topic, data))


def send(topic, data):
    client.publish(topic, json.dumps(data, ensure_ascii=False))
    add_log("송신", topic, data)


# ---------------- 화면에 표시하는 함수 ----------------

def show(label, text, ok=None):
    """상태 배지의 글자와 색을 바꾼다. ok: True=초록, False=빨강, None=회색"""
    color = GRAY if ok is None else (GREEN if ok else RED)
    label.configure(text=text, fg_color=color)


def add_log(kind, topic, data):
    now = datetime.now().strftime("%H:%M:%S")
    log.configure(state="normal")
    log.insert("end", f"{now}  {kind}  {topic}  {data}\n")
    log.see("end")  # 항상 마지막 줄이 보이게 스크롤
    log.configure(state="disabled")


def ppe_text(data):
    """{"helmet": .., "vest": ..} -> ("화면 글자", 정상 여부)"""
    missing = []
    if not data.get("helmet"):
        missing.append("안전모")
    if not data.get("vest"):
        missing.append("안전복")
    if missing:
        return " · ".join(missing) + " 미착용", False
    return "착용 정상", True


def update_stats(data):
    """입구 판정 결과 하나로 출입 통계를 갱신한다"""
    if stats["date"] != datetime.now().date():  # 날짜가 바뀌면 처음부터 다시 센다
        reset_stats()

    if data.get("helmet") and data.get("vest"):
        stats["pass"] += 1
    else:
        stats["deny"] += 1
        if not data.get("helmet"):
            stats["no_helmet"] += 1
        if not data.get("vest"):
            stats["no_vest"] += 1
    show_stats()


def reset_stats():
    stats.update({"date": datetime.now().date(), "pass": 0, "deny": 0, "no_helmet": 0, "no_vest": 0})
    show_stats()


def show_stats():
    total = stats["pass"] + stats["deny"]
    stat_values["pass"].configure(text=str(stats["pass"]))
    stat_values["deny"].configure(text=str(stats["deny"]))
    stat_values["rate"].configure(text=f"{stats['pass'] / total * 100:.0f}%" if total else "-")
    stat_values["no_helmet"].configure(text=str(stats["no_helmet"]))
    stat_values["no_vest"].configure(text=str(stats["no_vest"]))
    stat_date.configure(text=f"{stats['date']:%Y-%m-%d}")


def handle(topic, data):
    """메시지 하나를 받아서 알맞은 칸을 바꾼다"""
    if topic == "__connected__":
        show(conn_badge, "● 브로커 연결됨", True)
        return
    if topic == "__disconnected__":
        show(conn_badge, "● 연결 끊김 · 재접속 중", False)
        return

    add_log("수신", topic, data)
    if not isinstance(data, dict):
        return  # JSON이 아닌 메시지는 로그에만 남긴다

    if topic == "safety/entrance/result":
        show(entrance_result, *ppe_text(data))
        update_stats(data)

    elif topic == "safety/entrance/door":
        is_open = data.get("door") == "open"
        show(entrance_door, "열림" if is_open else "닫힘", None)

    elif topic == "safety/site/ppe":
        show(site_ppe, *ppe_text(data))

    elif topic == "safety/site/thermal":
        temp = data.get("max_temp", 0)
        show(site_temp, f"{temp:.1f} °C", temp < HOT_TEMP)

    elif topic == "safety/site/alarm":
        is_on = data.get("alarm") == "on"
        show(site_alarm, "켜짐" if is_on else "꺼짐", not is_on)

    elif topic == "safety/equipment/status":
        running = data.get("motor") == "running"
        show(equip_motor, "가동 중" if running else "정지", running)


def check_inbox():
    """0.1초마다 우체통을 확인해서 쌓인 메시지를 처리한다"""
    while not inbox.empty():
        topic, data = inbox.get()
        handle(topic, data)
    root.after(100, check_inbox)


# ---------------- 화면 만들기 ----------------

root = ctk.CTk(fg_color=BG)
root.title("AI 보호구 안전관리 - 중앙 서버")
root.geometry("1100x780")

F = "맑은 고딕"
font_title = ctk.CTkFont(family=F, size=22, weight="bold")
font_card = ctk.CTkFont(family=F, size=16, weight="bold")
font_body = ctk.CTkFont(family=F, size=14)
font_badge = ctk.CTkFont(family=F, size=14, weight="bold")
font_big = ctk.CTkFont(family=F, size=32, weight="bold")
font_small = ctk.CTkFont(family=F, size=12)

# --- 맨 위: 제목과 연결 상태 ---
header = ctk.CTkFrame(root, fg_color="transparent")
header.pack(fill="x", padx=24, pady=(20, 10))
ctk.CTkLabel(header, text="AI 보호구 안전관리 시스템", font=font_title).pack(side="left")
ctk.CTkLabel(header, text="  중앙 서버 대시보드", font=font_body, text_color=SUB).pack(side="left", pady=(6, 0))
conn_badge = ctk.CTkLabel(header, text="● 브로커 연결 중...", font=font_badge,
                          fg_color=GRAY, corner_radius=14, height=30, padx=14)
conn_badge.pack(side="right")

# --- 가운데: 파트별 카드 3개 ---
cards = ctk.CTkFrame(root, fg_color="transparent")
cards.pack(fill="x", padx=18)
cards.grid_columnconfigure((0, 1, 2), weight=1, uniform="card")


def make_card(title, pi_name, column):
    card = ctk.CTkFrame(cards, fg_color=CARD, corner_radius=16)
    card.grid(row=0, column=column, sticky="nsew", padx=6)
    card.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(card, text=title, font=font_card).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 0))
    ctk.CTkLabel(card, text=pi_name, font=font_small, text_color=SUB).grid(
        row=1, column=0, sticky="w", padx=18, pady=(0, 10))
    return card


def make_row(card, name, row):
    ctk.CTkLabel(card, text=name, font=font_body, text_color=SUB).grid(
        row=row, column=0, sticky="w", padx=18, pady=5)
    badge = ctk.CTkLabel(card, text="-", font=font_badge, fg_color=GRAY,
                         corner_radius=10, width=140, height=32)
    badge.grid(row=row, column=1, sticky="e", padx=18, pady=5)
    return badge


def make_buttons(card, row, buttons):
    box = ctk.CTkFrame(card, fg_color="transparent")
    box.grid(row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 16))
    for i, (text, color, command) in enumerate(buttons):
        box.grid_columnconfigure(i, weight=1)
        ctk.CTkButton(box, text=text, font=font_body, fg_color=color, height=36,
                      corner_radius=10, command=command).grid(row=0, column=i, sticky="ew", padx=6)


c1 = make_card("① 입구", "2번 파이 · rpi-jsm6049", 0)
entrance_result = make_row(c1, "보호구 판정", 2)
entrance_door = make_row(c1, "출입문", 3)

c2 = make_card("② 현장", "3번 파이 · rpi-kks2021", 1)
site_ppe = make_row(c2, "착용 감시", 2)
site_temp = make_row(c2, "최고 온도", 3)
site_alarm = make_row(c2, "현장 경보", 4)
make_buttons(c2, 5, [
    ("경보 켜기", RED, lambda: send("safety/site/alarm", {"alarm": "on"})),
    ("경보 끄기", GRAY, lambda: send("safety/site/alarm", {"alarm": "off"})),
])

c3 = make_card("③ 설비", "1번 파이 · JGH1628", 2)
equip_motor = make_row(c3, "모터", 2)
make_buttons(c3, 3, [
    ("설비 차단", RED, lambda: send("safety/equipment/cmd", {"cmd": "STOP"})),
    ("설비 해제", GREEN, lambda: send("safety/equipment/cmd", {"cmd": "RUN"})),
])

# --- 출입 통계 ---
stat_card = ctk.CTkFrame(root, fg_color=CARD, corner_radius=16)
stat_card.pack(fill="x", padx=24, pady=12)
top = ctk.CTkFrame(stat_card, fg_color="transparent")
top.pack(fill="x", padx=18, pady=(14, 4))
ctk.CTkLabel(top, text="출입 통계", font=font_card).pack(side="left")
stat_date = ctk.CTkLabel(top, text="", font=font_small, text_color=SUB)
stat_date.pack(side="left", padx=10, pady=(3, 0))
ctk.CTkButton(top, text="초기화", font=font_small, width=70, height=28, corner_radius=8,
              fg_color=GRAY, command=reset_stats).pack(side="right")

tiles = ctk.CTkFrame(stat_card, fg_color="transparent")
tiles.pack(fill="x", padx=12, pady=(4, 16))
stat_values = {}
items = [("pass", "통과", GREEN), ("deny", "거부", RED), ("rate", "통과율", BLUE),
         ("no_helmet", "안전모 미착용", "#f59e0b"), ("no_vest", "안전복 미착용", "#f59e0b")]
for i, (key, name, color) in enumerate(items):
    tiles.grid_columnconfigure(i, weight=1, uniform="tile")
    tile = ctk.CTkFrame(tiles, fg_color=BG, corner_radius=12)
    tile.grid(row=0, column=i, sticky="ew", padx=6)
    stat_values[key] = ctk.CTkLabel(tile, text="0", font=font_big, text_color=color)
    stat_values[key].pack(pady=(10, 0))
    ctk.CTkLabel(tile, text=name, font=font_small, text_color=SUB).pack(pady=(0, 10))

# --- 아래: 메시지 기록 ---
log_card = ctk.CTkFrame(root, fg_color=CARD, corner_radius=16)
log_card.pack(fill="both", expand=True, padx=24, pady=(0, 20))
ctk.CTkLabel(log_card, text="메시지 기록", font=font_card).pack(anchor="w", padx=18, pady=(14, 6))
log = ctk.CTkTextbox(log_card, font=ctk.CTkFont(family="Consolas", size=12),
                     fg_color=BG, corner_radius=10, state="disabled")
log.pack(fill="both", expand=True, padx=14, pady=(0, 14))


# ---------------- MQTT 시작 ----------------

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="server")
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.connect_async(BROKER, 1883)  # 브로커가 꺼져 있어도 창은 뜨고, 켜지면 알아서 접속
client.loop_start()


def on_close():
    client.loop_stop()
    client.disconnect()
    root.destroy()


root.protocol("WM_DELETE_WINDOW", on_close)  # 창 X 버튼을 누르면 정리하고 종료
show_stats()
check_inbox()
root.mainloop()
