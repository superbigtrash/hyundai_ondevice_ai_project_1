/* ============================================
 * ③ 설비 제어부 - 1번 파이 (JGH1628) / C - 통신 테스트용
 * - 서버의 차단/해제 명령을 받고, 결과를 다시 보고한다
 * 컴파일: gcc pi_equipment.c -o pi_equipment -lmosquitto
 * ============================================ */
#include <stdio.h>
#include <string.h>
#include <mosquitto.h>

#define BROKER "192.168.20.123"   /* 노트북 IP (바뀌면 수정 후 다시 컴파일) */

void send_msg(struct mosquitto *m, const char *topic, const char *msg)
{
    mosquitto_publish(m, NULL, topic, strlen(msg), msg, 0, false);
    printf("[송신] %s -> %s\n", topic, msg);
}

/* 브로커에 연결되면 자동으로 불린다 */
void on_connect(struct mosquitto *m, void *userdata, int rc)
{
    printf("브로커 연결됨: %d\n", rc);
    mosquitto_subscribe(m, NULL, "safety/equipment/cmd", 0);  /* 서버 명령 구독 */
}

/* 메시지가 오면 자동으로 불린다 */
void on_message(struct mosquitto *m, void *userdata, const struct mosquitto_message *msg)
{
    /* payload는 끝에 '\0'이 없으므로 길이만큼 복사해서 문자열로 만든다 */
    char payload[256];
    snprintf(payload, sizeof(payload), "%.*s", msg->payloadlen, (char *)msg->payload);
    printf("[수신] %s -> %s\n", msg->topic, payload);

    /* JSON 안에 STOP / RUN 글자가 있는지로 간단히 구분 */
    if (strstr(payload, "STOP")) {
        send_msg(m, "safety/equipment/status", "{\"motor\": \"stopped\"}");
    } else if (strstr(payload, "RUN")) {
        send_msg(m, "safety/equipment/status", "{\"motor\": \"running\"}");
    }
}

int main(void)
{
    mosquitto_lib_init();
    struct mosquitto *m = mosquitto_new("pi_equipment", true, NULL);

    /* 콜백 함수 등록 (파이썬의 client.on_connect = ... 와 같다) */
    mosquitto_connect_callback_set(m, on_connect);
    mosquitto_message_callback_set(m, on_message);

    if (mosquitto_connect(m, BROKER, 1883, 60) != MOSQ_ERR_SUCCESS) {
        printf("브로커 연결 실패\n");
        return 1;
    }

    mosquitto_loop_forever(m, -1, 1);  /* 메시지를 계속 기다린다 (Ctrl+C로 종료) */

    mosquitto_destroy(m);
    mosquitto_lib_cleanup();
    return 0;
}
