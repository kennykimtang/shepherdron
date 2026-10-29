Shepherdron 현장 운용 절차

> 비행 당일 이 문서를 순서대로 따릅니다. 건너뛰지 마세요.
>
> 주의 **시연이 실내라면 [INDOOR.md](INDOOR.md) 를 먼저 읽으세요.** GPS·고도·구조물 길이
> 전제가 전부 달라집니다. 이 문서의 지오펜스·고도 권장값도 실내에서는 쓸 수 없습니다.

---

0. 가장 중요한 것 : 소프트웨어 페일세이프를 믿지 마세요

이 프로젝트의 안전 장치는 **두 층**입니다. 그리고 **한 층은 조건부로만 동작합니다.**

| 층 | 담당 | 동작 조건 |
|---|---|---|
| 1차 (소프트웨어) | `MavlinkController` 반경·고도 제한, `GuidanceMission` 페일세이프 | **Pi ↔ Pixhawk 링크가 살아 있을 때만** |
| 2차 (펌웨어) | ArduPilot 지오펜스·배터리·RC 페일세이프 | **항상** |

**Pi가 죽거나 USB-TTL이 빠지면 1차 층은 통째로 사라집니다.** RTL 명령조차 보낼 수 없습니다.
그래서 §1의 ArduPilot 파라미터 설정은 **선택이 아니라 필수**입니다.

---

1. 최초 1회 : ArduPilot 파라미터

Mission Planner → CONFIG → Full Parameter List 에서 설정하고 **Write Params** 후 재부팅합니다.

> 주의 아래는 **권장값**입니다. 파라미터의 기본값·허용범위는 펌웨어 버전마다 다르므로
> [공식 파라미터 목록](https://ardupilot.org/copter/docs/parameters.html)에서 본인 버전을 확인하세요.

기체 구성 (4S · Quad X)
```
FRAME_CLASS       1       multicopter
FRAME_TYPE        1       quad X
BATT_MONITOR      4       전압 + 전류 (파워모듈 또는 FC 내장 센싱)
MOT_BAT_VOLT_MAX  16.8    4S 만충  (4 × 4.2 V)
MOT_BAT_VOLT_MIN  13.2    4S 방전  (4 × 3.3 V)
BRD_SAFETYENABLE  1       안전 스위치 사용 (없으면 0)
```

컴패니언 링크
```
SERIAL2_PROTOCOL  2       MAVLink2
SERIAL2_BAUD      921     불안정하면 115
```

지오펜스 : 소프트웨어 제한의 바깥 울타리
소프트웨어 제한보다 **조금 넓게** 잡아 소프트웨어가 먼저 걸리도록 하되,
소프트웨어가 죽어도 펜스가 받아내게 합니다.

야외 (소프트웨어 반경 100 m / 고도 30 m)
```
FENCE_ENABLE      1
FENCE_TYPE        3       고도 + 원형
FENCE_RADIUS      120
FENCE_ALT_MAX     35
FENCE_ACTION      1       RTL
```

실내 강당 (소프트웨어 반경 15 m / 고도 3.4 m : [INDOOR.md](INDOOR.md))
```
FENCE_ENABLE      1
FENCE_TYPE        3
FENCE_RADIUS      20
FENCE_ALT_MAX     3.8     천장 4.22 m 아래
FENCE_ACTION      1       RTL  (실내에서는 2 LAND 가 더 안전할 수 있음)
```
실내에서 RTL 은 홈 지점까지 수평 이동합니다. 좁은 공간에서는 `FENCE_ACTION=2`(LAND)
또는 `3`(BRAKE)이 더 안전한지 현장에서 판단하세요.

배터리 페일세이프 (4S 기준)
```
BATT_LOW_VOLT     14.0    3.5 V/셀 × 4
BATT_CRT_VOLT     13.2    3.3 V/셀 × 4
BATT_FS_LOW_ACT   2       RTL   (실내에서는 1 LAND 권장)
BATT_FS_CRT_ACT   1       LAND
```

조종기·지상국 링크 끊김
```
FS_THR_ENABLE     1       RC 신호 끊기면 RTL
FS_GCS_ENABLE     1       MAVLink 끊기면 RTL (5초 이상)
RTL_ALT           1500    복귀 고도 15 m (cm 단위). 실내는 250 (2.5 m)
```

> `FS_GCS_ENABLE`은 Pi가 heartbeat를 멈추면 트리거됩니다. **Pi가 죽었을 때 기체를
> 돌려세우는 유일한 장치**이므로 반드시 켜세요.

---

2. 비행 전날

- [ ] 배터리 완충 (4S 만충 16.8 V 확인)
- [ ] `pytest tests/` 통과 확인
- [ ] 노트북·Pi 코드 버전 일치 (`git log -1` 양쪽 비교)
- [ ] 지상 평면 캘리브레이션 파일 준비 ([VISION.md](VISION.md) §3-2)
- [ ] 비행 장소 확인 : [드론원스톱](https://drone.onestop.go.kr) 에서 비행금지구역 여부

---

3. 현장 설치 (프로펠러 없이)

1. **기체 조립** : [WIRING.md](WIRING.md) §7 조립 순서를 따릅니다.
2. **카메라 각도** : 45° 하향 고정 확인. 수직이면 사람이 6.5 px 라 검출이 안 됩니다.
3. **Wi-Fi 연결** : 노트북에서 Pi 에 ping 이 가는지 확인.
4. **배터리 연결** : 프로펠러는 아직 끼우지 않습니다.
5. **Pixhawk 부팅 확인** : GPS 3D fix, 위성 12개 이상.

소프트웨어 기동 순서

```bash
# ① 기체 (Pi) — 카메라 스트리밍
python scripts/stream_camera.py --source csi --width 1280 --height 720

# ② 기체 (Pi) — 판단·구동 에이전트
python shepherdron_pi.py --fc /dev/ttyUSB0 --ground <노트북-IP> --altitude 10

# ③ 지상 (노트북)
python shepherdron_ground.py --source http://<pi-ip>:8000/stream.mjpg --pi <pi-ip> \
       --calibration calibration/ground_plane.json
```

양쪽 모두 **`설정 점검 : OK`** 가 떠야 합니다. NG 면 그 자리에서 멈추고 원인을 고칩니다.

모터 회전 방향 확인 (프로펠러 없이)

- [ ] Mission Planner 의 Motor Test 로 1~4번을 하나씩 돌립니다
- [ ] [WIRING.md](WIRING.md) §6 **DETAIL A** 와 회전 방향 대조
- [ ] 방향이 틀리면 ESC 3선 중 **아무 2선을 바꿔** 끼웁니다

---

4. 프로펠러 장착

- [ ] **MF9545 (역)(역방향)** → M1 전방우측, M2 후방좌측
- [ ] **MF9545(정방향)** → M3 전방좌측, M4 후방우측
- [ ] 너트 토크 확인, 손으로 돌려 유격 확인

> 주의 엉뚱한 모터에 끼우면 **이륙 즉시 전복**합니다. 두 사람이 교차 확인하세요.

---

5. 첫 비행 (수동만)

**자율 모드를 켜지 않습니다.** 기체가 제대로 뜨는지만 봅니다.

- [ ] `STABILIZE` 로 1 m 호버링 : 기울어짐·진동 확인
- [ ] `LOITER` 로 위치 유지 확인
- [ ] 착륙 후 **모터 온도 확인** (손을 못 댈 정도면 중단)
- [ ] 비행 시간 기록 → 체공 예산(11.5분)과 대조

---

6. 자율 비행

역할 분담 : 세 사람

| 역할 | 하는 일 |
|---|---|
| **조종사** | 조종기를 **손에서 놓지 않습니다.** 모드 스위치에 손가락을 올려 둡니다 |
| **운용자** | 노트북 지상국 화면 감시, 경보 발생 보고 |
| **관측자** | 기체를 눈으로 추적, 주변 사람·장애물 감시 |

절차

- [ ] 조종사가 `STABILIZE` 로 이륙 → 10 m 상승
- [ ] 조종사가 `GUIDED` 로 전환 (이때부터 임무가 명령 가능)
- [ ] 운용자가 지상국 HUD 확인 : `구조물 STOWED`, `link` 지연 1초 미만
- [ ] 군중 역할 인원이 모여 과밀집 유발
- [ ] 기체가 이동 → 도달 → 전개 → 안내 → **수축** → 복귀

즉시 수동 전환해야 할 때

**조종기의 모드 스위치를 올리면 임무는 즉시 물러납니다.** 비행 명령을 하나도 내지
않고, 구조물만 접습니다. 조종권을 되찾아가지 않습니다.

- 기체가 예상 밖으로 움직일 때
- 사람·장애물에 접근할 때
- 진동·소음이 평소와 다를 때
- **판단이 서지 않을 때** ← 망설이지 말고 올리세요

---

7. 비행 후

- [ ] 배터리 분리 → 전압 확인 (4S 14.0 V, 셀당 3.5 V 아래면 과방전)
- [ ] 세션 로그 회수 : `logs/session_*.jsonl` (Pi 에서 노트북으로 복사)
- [ ] Pixhawk 비행 로그 회수 : SD 카드의 `.bin`
- [ ] 모터·프로펠러·배선 육안 점검

세션 로그 읽기

```bash
# 임무 상태 변화만
grep mission_state logs/session_*.jsonl | python -m json.tool --json-lines

# 경보가 켜진 시점
grep '"alert": true' logs/session_*.jsonl | head
```

기록되는 것: 임무 상태 전이와 이유, 비전 판단(인원수·밀집도·타겟 좌표),
기체 상태(모드·고도·배터리·링크 지연), 경고(관측 끊김·반경 초과).

---

8. 문제 해결

| 증상 | 확인할 것 |
|---|---|
| `설정 점검 : NG` | 출력된 항목을 그대로 고칩니다. `.env` 확인 |
| 기체가 안 움직임 | 모드가 `GUIDED` 인가? 지상국 HUD 의 `임무상태` 확인 |
| `STANDBY` 에서 안 빠짐 | 조종사가 수동 전환한 상태. 착륙해야 `IDLE` 복귀 |
| 상단 그리드가 `too far` | 고도가 높거나 입력이 320px. 640px 로 올리거나 고도를 낮춤 |
| `link` 지연이 계속 큼 | Wi-Fi 거리·간섭. `--quality` 낮추거나 해상도 축소 |
| 사람이 검출 안 됨 | 카메라 각도 45° 확인, `--conf` 낮춤, 입력 640px |
| 경보가 너무 자주 | `DENSITY_DANGER` 올리거나 `ALERT_ON_RATIO` 올림 |

---

9. 비상 시

1. **조종기 모드 스위치를 올립니다.** 임무가 즉시 물러납니다.
2. 수동으로 안전한 곳에 착륙시킵니다.
3. 제어가 안 되면 : 사람에게서 멀어지는 방향으로 스로틀을 내립니다.
4. 착륙 후 **배터리부터 분리**합니다.

> 기체보다 사람이 먼저입니다. 기체는 다시 만들 수 있습니다.
