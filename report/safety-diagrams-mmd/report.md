# 현장 안전 모니터링 시스템 설계 보고서

실제 작업자의 안전모와 안전복 착용 여부를 출입구와 현장에서 각각 판정하고, 결과를 모형 출입구와 경보 장치로 시연하는 시스템이다. 아래 그림은 Raspberry Pi 3대와 MQTT 서버를 사용하는 설계를 설명한다. 성능 수치와 시연 결과는 실측 후 기록한다.

| 구분 | 필수 기능 | 확장 기능 |
|---|---|---|
| 인식 | 출입구·현장 카메라의 사람별 보호구 판정 | 인원 집계, 온습도·열화상 기반 설비 이상 감지 |
| 제어 | 모형 출입구 개폐, LED, 부저 | 배연 팬, 추가 센서를 조합한 멀티센서 연동 |
| 시연 | 실제 사람의 보호구 착탈, 개방 보류·승인, 현장 경보 | 환경 이상 입력과 설비 반응 |

## 1. 시스템 전체 구성

PC에서 보호구 모델을 학습해 출입구 Pi A와 현장 Pi B에 배포한다. 시연자가 실제로 보호구를 착용하고 카메라 앞에 서면 두 Pi가 각각 현장에서 추론한다. Pi A는 모형 출입구를 제어하고, Pi C는 현장 LED와 부저를 구동한다. MQTT 브로커는 장치 사이의 판정 결과·명령·상태 메시지를 중계한다.

```mermaid
flowchart TB
    pc["PC｜보호구 모델 학습"]:::base
    a["Pi A｜출입구 판정"]:::base
    b["Pi B｜현장 감시"]:::base
    m["MQTT 브로커"]:::base
    c["Pi C｜경보·설비 제어"]:::base
    g["모형 출입구·LED"]:::base
    w["현장 LED·부저"]:::base
    f["확장｜배연 팬"]:::ext
    pc -->|"모델 배포"| a
    pc -->|"모델 배포"| b
    a -->|"개폐·표시"| g
    a -->|"출입 결과"| m
    b -->|"현장 상태"| m
    m -->|"제어 명령"| c
    c -->|"설비 상태"| m
    c -->|"경보"| w
    c -->|"확장"| f
    classDef base fill:#edf6f5,stroke:#71979a,color:#15343f
    classDef decision fill:#fff0c7,stroke:#af812d,color:#15343f
    classDef ext fill:#f3eef8,stroke:#9176a8,color:#15343f
```

*그림 1. 두 대의 Pi가 영상을 판정하고, 세 번째 Pi가 현장 경보와 설비를 제어한다.*  

## 2. 하드웨어 구성도

출입구 카메라와 디스플레이는 Pi A가 담당한다. Arduino는 센서 A의 거리와 센서 B의 통과 구역 상태를 읽고 모터를 제어한다. A·B는 출입구 동작도상의 센서 역할이다. 그 밖의 초음파 등 추가 센서를 조합하는 멀티센서 기능은 확장 검토 항목이다. 현장 카메라는 Pi B에 연결하고, 열화상·온습도 입력과 배연 팬은 확장 시 추가한다. 이 그림은 기능 연결도이며 핀 배치와 통신 인터페이스는 별도 설계 대상이다.

```mermaid
flowchart LR
    cam["출입구 카메라"]:::base
    a["Pi A｜출입구"]:::base
    ds["화면·출입구 LED"]:::base
    s["센서 A｜거리<br/>센서 B｜통과 구역"]:::base
    ar["Arduino"]:::base
    motor["모터 드라이버<br/>스텝 모터·모형 출입구"]:::base
    rgb["현장 카메라"]:::base
    ex["확장｜온습도·열화상"]:::ext
    b["Pi B｜현장"]:::base
    mq["MQTT 브로커"]:::base
    c["Pi C｜설비 제어"]:::base
    alarm["현장 LED·부저"]:::base
    fan["확장｜배연 팬"]:::ext
    cam -->|"영상"| a
    a -->|"판정 표시"| ds
    s -->|"측정"| ar
    a -->|"개폐 지시"| ar
    ar -->|"감지 상태"| a
    ar -->|"구동"| motor
    rgb -->|"영상"| b
    ex -->|"측정"| b
    a -->|"결과"| mq
    b -->|"결과"| mq
    mq -->|"명령"| c
    c -->|"경보"| alarm
    c -->|"확장"| fan
    classDef base fill:#edf6f5,stroke:#71979a,color:#15343f
    classDef decision fill:#fff0c7,stroke:#af812d,color:#15343f
    classDef ext fill:#f3eef8,stroke:#9176a8,color:#15343f
```

*그림 2. 입력 장치, 연산 보드, 모형 출력 장치의 기능 연결을 나타낸다.*  

## 3. 소프트웨어 구성도

Pi A와 Pi B의 카메라 처리부는 프레임에서 사람과 보호구를 검출한다. Pi A는 같은 사람의 안전모와 안전복을 연결해 연속 확인 조건을 적용한다. Pi B는 감시 원인을 독립적으로 갱신한다. 서버 측 실행 프로그램이 메시지를 처리하고, 브로커가 해당 토픽의 구독자에게 전달한다.

```mermaid
flowchart TB
    i["A · B｜카메라 입력"]:::base
    p["각 Pi의 YOLO 추론"]:::base
    a["A｜사람별 보호구 판정<br/>연속 프레임 확인"]:::base
    b["B｜작업자 상태 갱신"]:::base
    e["확장｜온습도·열화상 판단"]:::ext
    d["A｜화면 표시·출입구 제어"]:::base
    s["서버｜결과·명령 처리<br/>MQTT 중계"]:::base
    c["C｜경보·설비 제어<br/>상태 회신"]:::base
    i -->|"프레임"| p
    p -->|"출입구 검출"| a
    p -->|"현장 검출"| b
    e -->|"원인별 상태"| b
    a -->|"판정"| d
    a -->|"출입 결과"| s
    b -->|"현장 결과"| s
    s -->|"명령"| c
    c -->|"상태"| s
    classDef base fill:#edf6f5,stroke:#71979a,color:#15343f
    classDef decision fill:#fff0c7,stroke:#af812d,color:#15343f
    classDef ext fill:#f3eef8,stroke:#9176a8,color:#15343f
```

*그림 3. 영상 추론, 출입 정책, 현장 경보 정책, 장치 제어를 역할별로 구분한다.*  

## 4. 프로그램 코드 모듈 다이어그램

project.py는 전체 실행과 메시지 전송을 맡는 서버 측 프로그램의 가명이다. pi_entrance.py와 pi_site.py는 각 Pi에서 predict.py의 카메라·YOLO 추론 기능을 사용한다. Arduino의 센서·모터 제어 코드는 Pi A와 연동한다. pi_equipment.c는 Pi C에서 경보와 설비를 제어하고 상태를 전송한다. 선은 모듈 간 역할 관계로, 함수 호출이나 실제 저장소 경로를 지정하지 않는다.

```mermaid
flowchart TB
    s["서버｜project.py<br/>실행·메시지 전송"]:::base
    m["MQTT 브로커<br/>토픽 중계"]:::base
    a["Pi A｜pi_entrance.py<br/>출입 판정·표시·결과 송신"]:::base
    b["Pi B｜pi_site.py<br/>현장 감지·결과 송신"]:::base
    c["Pi C｜pi_equipment.c<br/>경보·설비 제어·상태 송신"]:::base
    pa["A｜predict.py<br/>카메라·YOLO 검출"]:::base
    pb["B｜predict.py<br/>카메라·YOLO 검출"]:::base
    ar["Arduino 제어 코드<br/>센서 판독·모터 구동"]:::base
    s ---|"메시지 연동"| m
    m ---|"토픽 연동"| a
    m ---|"토픽 연동"| b
    m ---|"토픽 연동"| c
    a -->|"검출 사용"| pa
    a -->|"장치 연동"| ar
    b -->|"검출 사용"| pb
    classDef base fill:#edf6f5,stroke:#71979a,color:#15343f
    classDef decision fill:#fff0c7,stroke:#af812d,color:#15343f
    classDef ext fill:#f3eef8,stroke:#9176a8,color:#15343f
```

*그림 4. 첨부 구성도에 적힌 가명으로 실행 위치와 모듈의 책임을 표시했다.*  

## 5. MQTT 토픽과 장치 역할

result와 door는 출입구, ppe·thermal·alarm은 현장 감시, cmd와 status는 설비 제어에 대응한다. 원도에는 토픽별 발행자·구독자 표가 없어 선은 장치와 브로커 사이의 토픽 묶음을 나타낸다. QoS와 메시지 형식도 확정 사양으로 두지 않았다.

```mermaid
flowchart TB
    s["서버 실행 프로그램"]:::base
    m["MQTT 브로커"]:::base
    a["Pi A｜출입구<br/>판정 결과·출입구 동작"]:::base
    b["Pi B｜현장 감시<br/>보호구·열화상(확장)·경보"]:::base
    c["Pi C｜설비 제어<br/>명령 수신·상태 송신"]:::base
    s ---|"메시지 연동"| m
    m ---|"result  /  door"| a
    m ---|"ppe  /  thermal  /  alarm"| b
    m ---|"cmd  /  status"| c
    classDef base fill:#edf6f5,stroke:#71979a,color:#15343f
    classDef decision fill:#fff0c7,stroke:#af812d,color:#15343f
    classDef ext fill:#f3eef8,stroke:#9176a8,color:#15343f
```

*그림 5. 각 연결에 첨부 구성도의 토픽 이름을 그대로 표시했다.*  

## 6. 출입구 동작 ① 접근과 보호구 판정

센서 A에서 70 cm보다 가까우면 “한 걸음 뒤로”를 안내한다. 90~150 cm 구간에 1초 정지하면 판정한다. 판정 중 구간을 벗어나거나 사람이 없으면 즉시 대기한다. 미착용은 빨간 LED와 미착용 항목으로 안내하고, 가림이나 낮은 신뢰도는 확인 불가로 표시한다. 보류 시 10초 이내 구간에 계속 있으면 재판정한다. 연속 확인 프레임 수 N과 안전복 세부 기준은 미정이다.

```mermaid
flowchart TB
    wait["대기 · 센서 A 측정"]:::base
    near{"70 cm 미만?"}:::decision
    back["한 걸음 뒤로 안내"]:::base
    zone{"90~150 cm에서<br/>1초 정지?"}:::decision
    cam["카메라 판정<br/>N프레임 연속 확인"]:::base
    ppe{"같은 사람의<br/>보호구 판정 결과?"}:::decision
    hold["개방 보류<br/>미착용 항목 또는 확인 불가 표시"]:::base
    retry{"10초 이내<br/>구간에 계속 있음?"}:::decision
    open["개방 승인<br/>스텝 모터 약 1초 → 그림 07"]:::base
    wait --> near
    near -->|"예"| back
    back -->|"재측정"| wait
    near -->|"아니요"| zone
    zone -->|"아니요"| wait
    zone -->|"예"| cam
    cam --> ppe
    ppe -->|"이탈·사람 없음"| wait
    ppe -->|"미착용·확인 불가"| hold
    hold --> retry
    retry -->|"예"| cam
    retry -->|"아니요"| wait
    ppe -->|"모두 착용·연속 확인"| open
    classDef base fill:#edf6f5,stroke:#71979a,color:#15343f
    classDef decision fill:#fff0c7,stroke:#af812d,color:#15343f
    classDef ext fill:#f3eef8,stroke:#9176a8,color:#15343f
```

*그림 6. 같은 사람의 안전모와 안전복이 N프레임 연속 확인돼야 모형 출입구가 열린다.*  

## 7. 출입구 동작 ② 통과 확인과 닫힘

사람이 지나간 뒤 센서 B가 1~2초 비면 닫힘을 시작한다. 개방 상태에서 10초 동안 아무도 지나가지 않은 경우에도 센서 B가 비어야 닫을 수 있다. 모터에 닫힘 명령을 보낸 것과 실제 닫힘 완료는 구분하며, 완료 확인 방법은 미정이다. 모형 동선에서 손이나 물체로 발생시킨 신호를 실제 입장 인원으로 집계하지 않는다.

```mermaid
flowchart TB
    open["개방 상태<br/>센서 B 확인"]:::base
    pass{"통과를<br/>감지했나?"}:::decision
    delay{"통과 후 1~2초<br/>연속으로 비었나?"}:::decision
    limit{"10초 동안<br/>미통과인가?"}:::decision
    clear{"센서 B가<br/>비었나?"}:::decision
    close["닫힘 구동"]:::base
    safe{"닫는 중<br/>사람 감지?"}:::decision
    re["즉시 정지·재개방"]:::base
    done{"닫힘 완료?"}:::decision
    wait["대기 복귀"]:::base
    open --> pass
    pass -->|"예"| delay
    delay -->|"아니요 · 확인 계속"| delay
    delay -->|"예"| close
    pass -->|"아니요"| limit
    limit -->|"아니요"| open
    limit -->|"예"| clear
    clear -->|"아니요"| open
    clear -->|"예"| close
    close --> safe
    safe -->|"예"| re
    re --> open
    safe -->|"아니요"| done
    done -->|"아니요"| safe
    done -->|"예"| wait
    classDef base fill:#edf6f5,stroke:#71979a,color:#15343f
    classDef decision fill:#fff0c7,stroke:#af812d,color:#15343f
    classDef ext fill:#f3eef8,stroke:#9176a8,color:#15343f
```

*그림 7. 센서 B가 비어 있을 때만 닫고, 닫는 중 사람이 감지되면 즉시 정지한 뒤 다시 연다.*  

## 8. 현장 감시와 경보 흐름

Pi B는 사람별 보호구 상태를 갱신하고 미착용과 확인 불가, 사람 없음, 영상 오류를 구분한다. 환경 입력에서는 공기 온습도와 물체 표면 온도를 구분한다. 경보 조건을 충족한 원인은 동시에 유지하고 발생·복귀 시각을 기록한다. 부저를 음소거해도 원인 상태는 유지한다. 고온은 과열 징후이며 화재 확정 기준과 배연 연동 조건은 별도 검토한다.

```mermaid
flowchart TB
    rgb["필수｜현장 RGB 카메라"]:::base
    ir["확장｜온습도·열화상"]:::ext
    p["Pi B｜작업자별 보호구 판정"]:::base
    t["범위 이탈·과열 징후 판단"]:::base
    st["원인별 최신 상태 갱신"]:::base
    q{"활성 경보<br/>원인이 있나?"}:::decision
    al["Pi C｜LED·부저 경보"]:::base
    ok["감시 상태 표시<br/>확인 불가·오류 별도 표시"]:::base
    log["발생·복귀 시각 기록<br/>다음 감시 주기로"]:::base
    rgb -->|"영상"| p
    ir -->|"측정"| t
    p -->|"보호구 상태"| st
    t -->|"환경 상태"| st
    st --> q
    q -->|"예"| al
    q -->|"아니요"| ok
    al --> log
    ok --> log
    classDef base fill:#edf6f5,stroke:#71979a,color:#15343f
    classDef decision fill:#fff0c7,stroke:#af812d,color:#15343f
    classDef ext fill:#f3eef8,stroke:#9176a8,color:#15343f
```

*그림 8. 보호구 감시는 필수이며 온습도와 설비 과열은 독립적인 확장 입력이다.*  

## 9. 사람을 이용한 시연 시나리오

필수 시연에서는 같은 사람이 보호구 하나를 벗은 상태로 접근한 뒤 안내를 보고 다시 착용한다. 이어 통과 신호, 모형 출입구의 닫힘, 현장 카메라의 미착용 경보를 차례로 확인한다. 확장 시연은 온도 또는 열화상 입력부터 별도로 시작한다. 실제 측정·시험 물체·모의 입력 중 어떤 방식을 사용했는지 표시하고, 팬 연동은 확장 구현 시에만 시연한다.

```mermaid
flowchart TB
    a["필수｜시연자 접근<br/>보호구 한 항목 미착용"]:::base
    b["개방 보류<br/>빨간 LED·미착용 항목 표시"]:::base
    c["보호구 착용 후 재판정<br/>모형 출입구 개방"]:::base
    d["통과 신호 확인<br/>비어 있으면 출입구 닫힘"]:::base
    e["현장 카메라에서 미착용 시연<br/>LED·부저 경보 확인"]:::base
    x["확장｜온습도·열화상 입력"]:::ext
    y["범위 이탈·설비 과열 표시"]:::base
    z["배연 연동 구현 시<br/>모형 팬 동작 확인"]:::base
    a --> b
    b --> c
    c --> d
    d --> e
    x --> y
    y --> z
    classDef base fill:#edf6f5,stroke:#71979a,color:#15343f
    classDef decision fill:#fff0c7,stroke:#af812d,color:#15343f
    classDef ext fill:#f3eef8,stroke:#9176a8,color:#15343f
```

*그림 9. 실제 사람의 보호구를 판정하고 출입 승인과 경보 결과를 모형에서 확인한다.*  

## 10. 출입구 전체 동작 흐름도

그림 6과 7의 연결 관계를 한 장으로 묶었다. 보류 뒤 재판정과 닫힘 중 재개방은 각각 카메라 판정 단계와 통과 감시 단계로 복귀한다.

```mermaid
flowchart TB
    wait["대기 · 센서 A 측정"]:::base
    near{"70 cm 미만?"}:::decision
    back["한 걸음 뒤로 안내"]:::base
    zone{"90~150 cm에서<br/>1초 정지?"}:::decision
    cam["카메라 판정<br/>N프레임 연속 확인"]:::base
    ppe{"같은 사람의<br/>보호구 판정 결과?"}:::decision
    hold["개방 보류<br/>미착용 항목 또는 확인 불가 표시"]:::base
    retry{"10초 이내<br/>구간에 계속 있음?"}:::decision
    open["개방 승인 · 스텝 모터 약 1초"]:::base
    passage_open["개방 상태<br/>센서 B 확인"]:::base
    passage_pass{"통과를<br/>감지했나?"}:::decision
    passage_delay{"통과 후 1~2초<br/>연속으로 비었나?"}:::decision
    passage_limit{"10초 동안<br/>미통과인가?"}:::decision
    passage_clear{"센서 B가<br/>비었나?"}:::decision
    passage_close["닫힘 구동"]:::base
    passage_safe{"닫는 중<br/>사람 감지?"}:::decision
    passage_re["즉시 정지·재개방"]:::base
    passage_done{"닫힘 완료?"}:::decision
    wait --> near
    near -->|"예"| back
    back -->|"재측정"| wait
    near -->|"아니요"| zone
    zone -->|"아니요"| wait
    zone -->|"예"| cam
    cam --> ppe
    ppe -->|"이탈·사람 없음"| wait
    ppe -->|"미착용·확인 불가"| hold
    hold --> retry
    retry -->|"예"| cam
    retry -->|"아니요"| wait
    ppe -->|"모두 착용·연속 확인"| open
    open --> passage_open
    passage_open --> passage_pass
    passage_pass -->|"예"| passage_delay
    passage_delay -->|"아니요 · 확인 계속"| passage_delay
    passage_delay -->|"예"| passage_close
    passage_pass -->|"아니요"| passage_limit
    passage_limit -->|"아니요"| passage_open
    passage_limit -->|"예"| passage_clear
    passage_clear -->|"아니요"| passage_open
    passage_clear -->|"예"| passage_close
    passage_close --> passage_safe
    passage_safe -->|"예"| passage_re
    passage_re --> passage_open
    passage_safe -->|"아니요"| passage_done
    passage_done -->|"아니요"| passage_safe
    passage_done -->|"예"| wait
    classDef base fill:#edf6f5,stroke:#71979a,color:#15343f
    classDef decision fill:#fff0c7,stroke:#af812d,color:#15343f
    classDef ext fill:#f3eef8,stroke:#9176a8,color:#15343f
```

*그림 10. 거리 측정에서 보호구 판정, 통과 확인, 닫힘과 대기 복귀까지의 전체 순환을 나타낸다.*  

## 검증 항목

- 다른 사람의 안전모와 안전복이 함께 보일 때 잘못 승인하는지 확인한다.
- 미착용·가림·사람 없음·영상 오류가 각각 올바르게 표시되는지 확인한다.
- 통과 후 닫힘, 미통과 10초, 닫힘 도중 재감지에 대해 기대 동작과 관찰 결과를 비교한다.
- 현장 감시에서는 부저 음소거 후에도 활성 경보 원인이 남는지 확인한다.
- 확장 시연에서는 공기 온습도와 물체 표면 온도의 입력 출처를 기록한다.

설계 근거는 제공된 README v0.3, 출입구 동작 흐름도, MQTT 프로그램 구성도와 Pi 3대 구성 결정이다.
