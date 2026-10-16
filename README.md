Shepherdron : 군중 밀집도 자율 안내 드론

[![CI](https://github.com/kennykimtang/shepherdron/actions/workflows/ci.yml/badge.svg)](https://github.com/kennykimtang/shepherdron/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)

> 군중 과밀집 구역을 비전으로 탐지하고, 해당 지점 상공으로 자율비행해
> 오리가미 구조물 전개와 LED·음성으로 대피를 유도하는 드론 시스템.
> 연세대학교 26년 2학기 창의제품설계 3분반 2조.

---

문서

| 문서 | 내용 |
|---|---|
| [TASK_BOARD.md](TASK_BOARD.md) | 파트별 작업 현황 (GitHub Issues/Projects와 연동) |
| [ROADMAP.md](ROADMAP.md) | 4단계 마일스톤 및 간트 차트 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 시스템 구조 : 지상/기체 역할 분담, 링크, 장애 동작 |
| [VISION.md](VISION.md) | 비전 코어 : 파이프라인·캘리브레이션·Pi 배포 |
| [FLIGHT.md](FLIGHT.md) | 비행 제어 : 측지 변환·안전 가드·SITL |
| [PAYLOAD.md](PAYLOAD.md) | 페이로드 : 전개/수축, 600mm 기구 선택지 |
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

---

시스템 구성

```
 ┌─ 비전 (Phase 1 · 완료) ──────────────────────────────────────┐
 │  Camera 3 Wide ─ YOLOv8n+ByteTrack ─ 원근보정 밀집도 ─ 타겟   │
 └──────────────────────────────┬───────────────────────────────┘
                                │  forward_m / right_m (기체 기준)
 ┌─ 비행 (Phase 2 · 코어 완료) ──▼───────────────────────────────┐
 │  Raspberry Pi 4 ─ MAVLink2 ─ KoA H743 ─ GUIDED goto     │
 └──────────────────────────────┬───────────────────────────────┘
                                │  호버링 도달 신호
 ┌─ 기구 (Phase 3) ─────────────▼───────────────────────────────┐
 │  LMB2036U 액추에이터 ─ 오리가미 전개 + WS2812B LED + 음성     │
 └──────────────────────────────────────────────────────────────┘
```

| 항목 | 사양 |
|---|---|
| 기체 | F450 쿼드 X · AIR2213 920KV ×4 · T9545/T9545R |
| 전원 | 4S 14.8 V · AUW 1,463 g · T/W 2.32:1 · 체공 5.3분 (3300 mAh 권장) |
| 제어 | KoA H743 (ArduCopter 4.x) + Raspberry Pi 4 2GB |
| 인지 | Camera Module 3 Wide (102° H) · YOLOv8n NCNN 320px ≈ 8–10 FPS |

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
