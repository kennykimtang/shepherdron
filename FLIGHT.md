# 🚁 Shepherdron 비행 제어 (Phase 2)

> 비전이 낸 **기체 기준 미터 오프셋** → GPS 좌표 → GUIDED 유도 비행 → 도달 판정 → 복귀

---

## 1. 비전과의 접점

비전 모듈은 이미 픽셀이 아니라 **기체 기준 미터**를 내보냅니다.

```python
result = pipeline.process(frame)          # vision.CrowdPipeline
if result.alert_rising_edge and result.target.has_ground_fix:
    result.target.forward_m   # 기수 방향 +m
    result.target.right_m     # 우현 방향 +m
```

비행 모듈은 여기에 기체의 **현재 위치와 기수 방위**를 합쳐 GPS 좌표로 만듭니다.

```python
from flight import target_from_body_offset

target = target_from_body_offset(
    origin=vehicle_position,   # GeoPoint
    yaw_deg=vehicle_heading,
    forward_m=result.target.forward_m,
    right_m=result.target.right_m,
    alt_m=10.0,
)
```

> ⚠️ **오프셋은 기체 기준이라 매 프레임 다시 재야 합니다.**
> 한번 잰 오프셋을 기체가 이동한 뒤에도 재사용하면 목표가 함께 움직여
> 영영 도달하지 못합니다. 실제 비전은 접근할수록 오프셋이 줄어드는 것이 정상입니다.

---

## 2. 구성

```
flight/
├── geodesy.py             기체 기준 오프셋 ↔ 위경도, 거리/방위, 반경 제한
├── mavlink_controller.py  Pixhawk 연결, 모드 전환, arm/takeoff/goto, 안전 가드
├── mission.py             유도 임무 상태기계 (비전 → 비행 → 전개 훅)
└── sitl_demo.py           SITL 로 전 구간을 돌려보는 실행기
```

### 상태기계

```
 IDLE ─경보─> NAVIGATING ─도달─> HOVERING ─유지─> RETRACTING ─접힘─> RETURNING
   ^              │               │                 │                 │
   │         재조준 │          구조물 전개 │          접히기 전엔 │ 착륙
   │     (군중 이동) │          + LED/음성 │           RTL 금지  │
   └──────────────┴───────────────┴─────────────────┴─────────────────┘
                   링크 끊김 / 배터리 부족 → FAILSAFE → RTL
```

상태 전이는 전부 명시적입니다. "아마 도착했겠지"로 다음 단계로 넘어가지 않습니다.

---

## 3. 안전 설계

실제 기체를 움직이는 코드이므로 모든 명령 앞에 가드를 둡니다.

| 가드 | 내용 |
|---|---|
| **반경 제한** | goto 목표를 홈 기준 `max_radius_m`(기본 100 m) 안으로 잘라냅니다. 비전이 틀린 타겟을 내도 기체가 시야 밖으로 날아가지 않습니다 |
| **고도 제한** | `min_altitude_m` ~ `max_altitude_m`(기본 3~30 m) 밖은 거부 |
| **사전 점검** | GPS fix, 위성 수, 배터리, heartbeat를 보고 거부 |
| **모드 검증** | 전환 명령을 보내고 **실제로 바뀌었는지 확인**합니다. MAVLink 명령은 자주 무시됩니다 |
| **링크 감시** | heartbeat가 끊기면 어느 상태에서든 FAILSAFE → RTL |
| **재조준 제한** | 타겟이 `retarget_distance_m` 이상 움직였을 때만, 최소 간격을 두고 재명령 |
| **쿨다운** | 임무 종료 후 `mission_cooldown_s` 동안 새 경보를 무시 |
| **dry_run** | 실제 전송 없이 로그만 남깁니다. SITL 연결 전 로직 검증용 |

```python
SafetyLimits(
    max_radius_m=100.0,       # 홈에서 벗어날 수 있는 최대 거리
    min_altitude_m=3.0,
    max_altitude_m=30.0,      # 국내 제한(150 m)보다 훨씬 보수적
    min_battery_pct=25,
    min_satellites=8,
    heartbeat_timeout_s=3.0,
)
```

> **반경 제한이 실제로 받아내는 상황:** 고도를 12 m가 아니라 1200 m로 잘못 주면
> 비전 오프셋이 100배로 폭주합니다. 그대로 goto가 나가면 기체가 5 km 밖으로 날아갑니다.
> `test_runaway_vision_target_is_contained`가 이 경로를 검증합니다.

---

## 4. SITL 시뮬레이션

하드웨어 없이 Phase 2 완료 기준("타겟 좌표로 10 m 고도 이동 후 호버링")을 검증합니다.

### 설치 (최초 1회)

```bash
git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git ~/ardupilot
cd ~/ardupilot && Tools/environment_install/install-prereqs-mac.sh -y   # Linux: install-prereqs-ubuntu.sh
. ~/.profile
```

### 실행

```bash
# 터미널 1 — 가상 기체 기동 (연세대 신촌 좌표)
./scripts/run_sitl.sh

# 터미널 2 — 유도 임무 전 구간 실행
python -m flight.sitl_demo
python -m flight.sitl_demo --forward 40 --right -25 --altitude 12
```

데모는 가짜 과밀집 경보를 주입해 이륙 → 유도 → 도달 → 호버링 → 복귀까지 돌립니다.
도달 시점에 `[PHASE 3] 액추에이터 전개 지점` 로그가 찍히는데, 여기가 기구부가 붙을 자리입니다.

---

## 5. 실기 연결 (Pixhawk)

```python
from flight import MavlinkController, SafetyLimits

ctl = MavlinkController("/dev/ttyUSB0", baud=921600)   # W12, USB-TTL 3.3V FTDI
ctl.connect()
```

배선과 파라미터는 [WIRING.md](WIRING.md) §4-1을 따릅니다.

```
SERIAL2_PROTOCOL = 2     # MAVLink2
SERIAL2_BAUD     = 921   # 불안정하면 115
```

⚠️ USB-TTL 케이블의 **5 V 선은 연결하지 마세요** — 역급전 위험.

---

## 6. 테스트

하드웨어도 SITL도 없이 수 초 안에 끝납니다.

```bash
pytest tests/test_geodesy.py tests/test_mavlink_controller.py \
       tests/test_mission.py tests/test_flight_integration.py -v
```

| 파일 | 검증 내용 |
|---|---|
| `test_geodesy.py` | 기수 회전에 따른 축 변환, 위경도 환산, 방위각, 반경 제한, 역변환 왕복 |
| `test_mavlink_controller.py` | 사전 점검, goto 거부 조건, 반경/고도 클램프, 도달 판정, 링크 상태 |
| `test_mission.py` | 상태 전이 전 구간, 재조준 조건, 쿨다운, 페일세이프 |
| `test_flight_integration.py` | **움직이는 가짜 기체로 IDLE→IDLE 한 사이클 완주** |

---

## 7. 남은 작업

- [ ] **[NAV-01]** SITL 설치 후 `flight.sitl_demo` 실제 완주 확인 ([#4](https://github.com/kennykimtang/shepherdron/issues/4))
- [ ] **[NAV-02]** Pixhawk 실기 TELEM2 통신 및 921600 안정성 확인 ([#5](https://github.com/kennykimtang/shepherdron/issues/5))
- [x] 전개 상태로 복귀하지 않도록 RETRACTING 상태 추가 ([PAYLOAD.md](PAYLOAD.md))
- [ ] **[NAV-05]** 정밀 호버링 — 현재는 RTL에 의존, 위치 유지 정확도 측정 필요
- [ ] 비전 파이프라인에 `pipeline.set_altitude()`로 기압계 고도를 주입하는 배선
- [ ] 조종기 개입 감지 → `mission.abort()` 연동
