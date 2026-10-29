Shepherdron : 군중 밀집도 자율 안내 드론

[![CI](https://github.com/kennykimtang/shepherdron/actions/workflows/ci.yml/badge.svg)](https://github.com/kennykimtang/shepherdron/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)

> 군중 과밀집 구역을 비전으로 탐지하고, 해당 지점 상공으로 자율비행해
> 오리가미 구조물 전개와 LED·음성으로 대피를 유도하는 드론 시스템.
> 연세대학교 26년 2학기 창의제품설계 3분반 2조.

---

현재 상태

소프트웨어는 대부분 올라왔습니다. 남은 일은 거의 전부 **실기 검증과 기구 제작**입니다.
테스트 298건이 하드웨어 없이 돌아갑니다.

| Phase | 내용 | 상태 |
|---|---|---|
| 1 비전 | 검출·추적, 원근보정 밀집도, 타겟 산출 | 코어 완료 : 현장 튜닝 남음 |
| 2 비행 | 측지 변환, 안전 가드, 상태기계, 실내 프로파일 | 코어 완료 : 실기 검증 남음 |
| 3 기구 | 전개/수축 제어 추상화 | 소프트웨어 완료 : **기구 방식 미결정** |
| 4 통합 | 지상/기체 역할 분리, 링크 | 완료 : 현장 시연 남음 |

확정된 전제

| 항목 | 내용 |
|---|---|
| 시연 장소 | **실내** 계단식 강당, 천장 4.22~4.43 m → 최대 비행고도 3.4 m |
| 동력계 | 4S 14.8 V + AirGear 355 : 정지추력 4,932 g, T/W 3.37, 체공 11.5분 |
| 비행제어기 | KoA H743 (핀맵 제조사 매뉴얼 확인 필요) |
| 연산 위치 | 노트북이 YOLO, 기체가 판단·구동 |
| 카메라 | 45도 하향 (수직은 사람이 6.5 px라 검출 불가) |

지금 막고 있는 것

| | 내용 | 막는 범위 |
|:-:|---|---|
| 1 | **옵티컬 플로우 센서 미구매** : 실내는 GPS가 없어 이것 없이는 자율비행 불가 ([#23](https://github.com/kennykimtang/shepherdron/issues/23)) | Phase 2 실내 검증 |
| 2 | **기구 방식 미결정** : 정해져야 재료·구동부를 주문할 수 있음 ([#9](https://github.com/kennykimtang/shepherdron/issues/9)) | Phase 3 전체 |
| 3 | **KoA H743 핀맵 미확인** : TELEM 포트 번호를 몰라 결선 확정 불가 ([#5](https://github.com/kennykimtang/shepherdron/issues/5)) | 조립 |

---

추가 구매 목록

이미 확보 : AirGear 355 · F450 프레임 · 랜딩 스키드 · KoA H743 · 4S 2800 mAh ·
iMax B6 충전기 · RadioMaster Pocket · Raspberry Pi 4

구매 예정 : Camera Module 3 Wide · 5V 3~5A UBEC · USB-TTL 케이블

아래는 **그 외에 없으면 프로젝트가 성립하지 않는 것**입니다.

| 우선 | 품목 | 이유 |
|:-:|---|---|
| 1 | **수신기** (SBUS 출력, FrSky D16 호환) | 조종기만으로는 기체가 안 움직임. 수동 개입이 최종 안전장치 |
| 1 | **microSD 32 GB 이상** (A1/A2) | Pi OS. 저가 카드는 비행 중 파일시스템이 깨짐 |
| 1 | **XT60 커넥터 + 실리콘 와이어** (14/18 AWG) | 배터리·PDB·UBEC 배선 |
| 2 | **옵티컬 플로우 + 하향 거리계** | 실내는 GPS 불가. 없으면 자율비행 시연 자체가 불가능 |
| 2 | **프로펠러 가드** | 실내에서 사람 근처를 남. 선택이 아님 |
| 3 | **(선택)WS2812B 30 LED + 74AHCT125** | 방향 유도. Pi의 3.3 V는 LED 문턱 3.5 V 미달이라 시프터 필수 |
| 3 | **(선택)MAX98357A + 3 W 4 Ω 스피커** | 음성 안내 |
| 3 | **4S 2800 mAh 배터리 1개 추가 (해당사항없음 -> 삭제 얘정)** | 체공 12분인데 충전에 1시간. 리허설+시연을 하루에 하면 부족 (발표시간 7분 이하 -> 해당사항없음) |
| 4 | **페이로드 구동부** | 기구 방식 결정 후 ([#9](https://github.com/kennykimtang/shepherdron/issues/9)) |

먼저 확인하고 사세요 : **파워모듈 · PDB · 안전스위치** — KoA H743 / F450 키트에 내장일 수 있습니다.

사지 않아도 됩니다 : **GPS**(실내) · **텔레메트리 모듈**(Pi가 Wi-Fi로 MAVLink 중계) ·
**Pi 쿨링 팬**(YOLO가 지상으로 가서 히트싱크면 충분)

근거와 상세는 [PURCHASE.md](PURCHASE.md)

---

문서

| 문서 | 내용 |
|---|---|
| [TASK_BOARD.md](TASK_BOARD.md) | 파트별 작업 현황 (GitHub Issues/Projects와 연동) |
| [ROADMAP.md](ROADMAP.md) | 4단계 마일스톤 및 간트 차트 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 시스템 구조 : 지상/기체 역할 분담, 링크, 장애 동작 |
| [VISION.md](VISION.md) | 비전 코어 : 파이프라인·캘리브레이션·Pi 배포 |
| [FLIGHT.md](FLIGHT.md) | 비행 제어 : 측지 변환·안전 가드·SITL |
| [PAYLOAD.md](PAYLOAD.md) | 페이로드 : 전개/수축, 기구 방식 선택지 |
| [OPERATIONS.md](OPERATIONS.md) | 현장 운용 : 비행 절차·ArduPilot 설정·문제 해결 |
| [INDOOR.md](INDOOR.md) | 실내 시연 : GPS 없는 비행·고도 제약·안전 구성 |
| [PURCHASE.md](PURCHASE.md) | 추가 구매 목록 : 필수 항목·확인 사항·불필요 항목 |
| [WIRING.md](WIRING.md) | 결선 명세 : 배선표 23선·핀맵·조립 순서 |
| [HARDWARE_SPEC.md](HARDWARE_SPEC.md) | 부품 검증 : BOM·추력/전력 예산·검증 근거 |

---

빠른 시작

```bash
git clone https://github.com/kennykimtang/shepherdron.git
cd shepherdron

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # 필요한 값만 수정

# 노트북 웹캠으로 바로 확인
python main.py --source 0

# 스마트폰 IP Webcam (같은 Wi-Fi 필요)
python main.py --source http://192.168.0.25:8080/video
```

> IP Webcam 연결 : 안드로이드는 IP Webcam, iOS는 IP Camera 앱을 설치하고
> Start server를 누른 뒤 표시된 주소 뒤에 `/video`를 붙입니다.

테스트는 모델 가중치 없음.

```bash
pytest tests/ -v
```

실제 시연 구성 (지상/기체 분리)

```bash
# 기체 (Pi) : 카메라 스트리밍
python scripts/stream_camera.py --source csi --width 1280 --height 720

# 기체 (Pi) : 판단·구동 에이전트 (실내)
python shepherdron_pi.py --fc /dev/ttyUSB0 --ground <노트북-IP> \
       --indoor --ceiling 4.22 --altitude 2.5

# 지상 (노트북) : YOLO 전담
python shepherdron_ground.py --source http://<pi-ip>:8000/stream.mjpg --pi <pi-ip> \
       --calibration calibration/ground_plane.json
```

하드웨어 없이 전체 연동을 확인하려면

```bash
python shepherdron_pi.py --fc udp:127.0.0.1:14550 --dry-run --ground 127.0.0.1 --payload sim &
python shepherdron_ground.py --source 0 --pi 127.0.0.1
```

---

시스템 구성

```
  지상 노트북                              기체
 ┌──────────────────────┐             ┌──────────────────────────────┐
 │ YOLOv8n + ByteTrack  │◀── MJPEG ───│ Camera 3 Wide (45도 하향)      │
 │ 원근보정 밀집도          │             │                              │
 │ 과밀집 판정             │─── 관측 ───▶ │ Raspberry Pi 4               │
 └──────────────────────┘    UDP      │   픽셀→미터, 임무 상태기계         │
   "무엇을 보았는가" 만 전달                │              │ MAVLink2      │
   비행 명령은 보내지 않음                  │   KoA H743 ──┘ 비행           │
                                       │              │               │
                                       │   페이로드 전개 + LED + 음성      │
                                       └──────────────────────────────┘
```

링크가 끊겨도 기체는 마지막 타겟까지 간 뒤 타임아웃으로 안전 복귀합니다.
상세는 [ARCHITECTURE.md](ARCHITECTURE.md)

| 항목 | 사양 |
|---|---|
| 기체 | F450 쿼드 X · AIR2213 KV1000 ×4 · MF9545 접이식 프로펠러 |
| 전원 | 4S 14.8 V 2800 mAh · AUW 1,463 g · T/W 3.37:1 · 체공 11.5분 |
| 제어 | KoA H743 (ArduCopter 4.x) + Raspberry Pi 4 2GB |
| 인지 | Camera Module 3 Wide (102° H, 45도 하향) · 지상 노트북에서 YOLOv8n |

---

구조

```text
shepherdron/
├── vision/
│   ├── detector.py          YOLOv8n + ByteTrack 인물 검출/추적
│   ├── density_analyzer.py  그리드 분할, 원근 보정 persons/m² 판정
│   ├── geometry.py          지상 평면 호모그래피, 픽셀→미터 변환
│   ├── stability.py         경보 히스테리시스, 인원수·타겟 평활
│   ├── pipeline.py          위 전부를 묶는 CrowdPipeline
│   ├── camera.py            CSI(Picamera2) / USB / IP 스트림 백엔드
│   └── stream_handler.py    저지연 멀티스레드 스트림 수신기
├── hardware/
│   └── payload.py           전개 구조물 추상화 (기구 방식 무관)
├── flight/
│   ├── geodesy.py           기체 기준 오프셋 ↔ 위경도, 반경 제한
│   ├── mavlink_controller.py Pixhawk 연결, 모드 전환, 안전 가드
│   ├── mission.py           유도 임무 상태기계
│   └── sitl_demo.py         SITL 전 구간 실행기
├── link/
│   ├── protocol.py          VisionReport / TelemetryReport
│   ├── udp.py               UDP 송수신, 신선도·순서 판별
│   └── bridge.py            픽셀 보고 → 미터 타겟 (기체 고도 사용)
├── scripts/
│   ├── stream_camera.py     기체 카메라 MJPEG 스트리밍
│   ├── calibrate_ground.py  지상 평면 캘리브레이션 (클릭 4점)
│   ├── export_ncnn.py       라즈베리파이용 NCNN 내보내기
│   ├── run_sitl.sh          ArduPilot SITL 기동
│   └── run_pi.sh            Pi 온보드 실행기
├── tests/                   pytest : 가중치 없이 로직 검증
├── shepherdron_ground.py    지상국 : YOLO 전담
├── shepherdron_pi.py        기체 에이전트 : 판단·구동 전담
├── main.py                  단일 기기 실행기 (개발·튜닝용)
└── config.py                설정 (.env 로 덮어쓰기)
```

---

협업 규칙

1. 브랜치 : `feat/<파트>-<작업>` 형식. 예: `feat/nav-mavlink-goto`
2. 이슈 : 작업 시작 전 GitHub Issue를 만들고 자신에게 할당.
3. PR : 본문에 `Resolves #<이슈번호>`를 적으면 머지 시 이슈가 자동으로 클로징.
4. 테스트 : 푸시 전 `pytest tests/`가 통과하는지 확인합니다. CI가 모든 PR에서 다시 테스트
5. main 직접 푸시 금지 -> 반드시 PR로 배포.

| 파트 | 라벨 | 담당 영역 |
|---|---|---|
| 비전 | `part:vision` | YOLO 검출·추적, 밀집도, 캘리브레이션 |
| 항법 | `part:nav` | MAVLink, 비행 제어, SITL |
| 하드웨어 | `part:hardware` | 배선, 액추에이터, LED/오디오 |
| 문서 | `part:docs` | 문서, 발표자료, 시연 |
