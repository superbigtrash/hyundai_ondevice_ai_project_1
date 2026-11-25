# ============================================
# ① 입구 제어부 - 2번 파이 (rpi-jsm6049) / Python - 통신 테스트용
# - 보호구 판정 결과, 문 상태를 서버로 보낸다
# ============================================
import json
import paho.mqtt.client as mqtt

BROKER = "192.168.20.123"  # 노트북 IP (바뀌면 ipconfig로 확인 후 수정)


def send(client, topic, data):
    client.publish(topic, json.dumps(data, ensure_ascii=False))
    print(f"[송신] {topic} -> {data}")


def on_connect(client, userdata, flags, reason_code, properties):
    print("브로커 연결됨:", reason_code)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pi_entrance")
client.on_connect = on_connect
client.connect(BROKER, 1883)
client.loop_start()  # 통신은 뒤에서 알아서 돌게 하고, 아래 while문을 실행

while True:
    key = input("1: 판정 통과  2: 판정 실패  3: 문 열림  4: 문 닫힘  > ")

    if key == "1":
        send(client, "safety/entrance/result", {"helmet": True, "vest": True})
    elif key == "2":
        send(client, "safety/entrance/result", {"helmet": False, "vest": True})
    elif key == "3":
        send(client, "safety/entrance/door", {"door": "open"})
    elif key == "4":
        send(client, "safety/entrance/door", {"door": "closed"})
