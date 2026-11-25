# ============================================
# ② 현장 감시부 - 3번 파이 (rpi-kks2021) / Python - 통신 테스트용
# - 착용 감시 결과, 열화상 결과를 서버로 보낸다
# - 서버의 경보 명령을 받는다
# ============================================
import json
import paho.mqtt.client as mqtt

BROKER = "192.168.20.123"  # 노트북 IP (바뀌면 ipconfig로 확인 후 수정)


def send(client, topic, data):
    client.publish(topic, json.dumps(data, ensure_ascii=False))
    print(f"[송신] {topic} -> {data}")


def on_connect(client, userdata, flags, reason_code, properties):
    print("브로커 연결됨:", reason_code)
    client.subscribe("safety/site/alarm")  # 서버의 경보 명령


def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())
    print(f"\n[수신] {msg.topic} -> {data}")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pi_site")
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, 1883)
client.loop_start()

while True:
    key = input("1: 착용 정상  2: 안전모 미착용  3: 정상 온도  4: 고온 감지  > ")

    if key == "1":
        send(client, "safety/site/ppe", {"helmet": True, "vest": True})
    elif key == "2":
        send(client, "safety/site/ppe", {"helmet": False, "vest": True})
    elif key == "3":
        send(client, "safety/site/thermal", {"max_temp": 36.5})
    elif key == "4":
        send(client, "safety/site/thermal", {"max_temp": 65.0})
