# ============================================
# 중앙 서버 (노트북) - 통신 테스트용
# - 모든 파이의 메시지를 받아서 화면에 출력
# - 키보드로 현장/설비 파이에 명령을 보낸다
# ============================================
import json
import paho.mqtt.client as mqtt

BROKER = "localhost"


def send(client, topic, data):
    client.publish(topic, json.dumps(data, ensure_ascii=False))
    print(f"[송신] {topic} -> {data}")


def on_connect(client, userdata, flags, reason_code, properties):
    print("브로커 연결됨:", reason_code)
    client.subscribe("safety/#")  # 모든 토픽 수신


def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())
    print(f"\n[수신] {msg.topic} -> {data}")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="server")
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, 1883)
client.loop_start()

while True:
    key = input("1: 설비 차단  2: 설비 해제  3: 현장 경보 켜기  4: 현장 경보 끄기  > ")

    if key == "1":
        send(client, "safety/equipment/cmd", {"cmd": "STOP"})
    elif key == "2":
        send(client, "safety/equipment/cmd", {"cmd": "RUN"})
    elif key == "3":
        send(client, "safety/site/alarm", {"alarm": "on"})
    elif key == "4":
        send(client, "safety/site/alarm", {"alarm": "off"})
