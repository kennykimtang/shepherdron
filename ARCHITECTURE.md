# 🏗️ Shepherdron 시스템 구조

> **결정일 2026-10-13** — 비전 연산은 지상 노트북, 판단과 구동은 기체.

---

## 1. 역할 분담

```
┌─ 지상 (노트북) ────────────────┐      ┌─ 기체 ──────────────────────────────┐
│                               │      │                                     │
│  MJPEG 영상 수신               │◀─────│  Camera 3 Wide ─ scripts/stream_camera.py
│       ↓                       │ Wi-Fi│                                     │
│  CrowdPipeline                │      │  shepherdron_pi.py                  │
│   YOLOv8n + ByteTrack         │      │   ├ VisionBridge  픽셀 → 미터        │
│   원근보정 밀집도               │      │   ├ GuidanceMission  상태기계        │
│   경보 히스테리시스             │      │   └ 페이로드 전개                    │
│       ↓                       │      │          ↓                          │
│  VisionReport ────────────────│─────▶│  MavlinkController                  │
│  "무엇을 보았는가" 만           │ UDP  │          ↓                          │
│                               │      │  Pixhawk 2.4.8  (비행)              │
│  shepherdron_ground.py        │◀─────│  TelemetryReport (HUD 용)           │
└───────────────────────────────┘      └─────────────────────────────────────┘
```

| | 지상 노트북 | 라즈베리파이 4 | Pixhawk |
|---|---|---|---|
| **역할** | 지각 (perception) | 판단 + 구동 | 비행 |
| **담당** | YOLO, 밀집도, 경보 판정 | 상태기계, 페일세이프, 페이로드 I/O | 자세, 모터, GPS |
| **없으면** | 새 관측이 끊김 (기체는 계속 동작) | 임무 불가 | 비행 불가 |

---

## 2. 왜 이렇게 나눴는가

### 연산은 노트북으로

Pi 4에서 YOLOv8n은 320px NCNN으로도 **8~10 FPS**가 한계입니다. 노트북(MPS)은 10배 이상 빠릅니다.
임무상 8 FPS면 충분하지만(경보 판정에 약 2초가 필요하고 군중은 그 사이 사라지지 않음),
굳이 느린 쪽에서 돌릴 이유가 없습니다.

### 판단은 기체에

**이게 핵심입니다.** 상태기계까지 노트북에 두면 Wi-Fi가 끊기는 순간 기체가 공중에 방치됩니다.

| | 비행 중 링크 끊김 |
|---|---|
| 노트북이 상태기계까지 보유 | Pi가 뭘 해야 할지 모름 ❌ |
| **기체가 상태기계 보유** | 마지막 타겟까지 계속 → 90초 타임아웃 → 자동 RTL ✅ |

실제로 검증했습니다. 지상국을 끈 뒤에도 기체는 40초간 마지막 타겟을 유지하며 비행했습니다.

### 링크는 관측만 나른다

`VisionReport`에는 `arm`, `takeoff`, `goto`, `mode` 같은 **비행 명령 필드가 아예 없습니다.**
노트북이 오작동하거나 링크가 탈취돼도 최악의 결과는 "잘못된 군중 위치 보고"이고,
그건 `MavlinkController`의 반경 제한(기본 100 m)이 막습니다. 테스트로 고정해 두었습니다.

### 미터가 아니라 픽셀을 보낸다

지상 거리(미터)를 구하려면 기체의 AGL 고도가 필요한데, 그건 **Pi만 압니다.**
노트북이 미터를 보내려면 먼저 고도를 받아와야 하므로 왕복 의존이 생기고,
텔레메트리가 늦으면 타겟이 틀어집니다.

→ 노트북은 **"화면 어디에서 보았는가"(픽셀)**만 보내고, 고도를 아는 Pi가 미터로 환산합니다.
고도를 모르면 `has_ground_fix`가 False가 되어 **비행 명령 자체가 나가지 않습니다.**

---

## 3. 실행

### 기체 (라즈베리파이)

```bash
# 터미널 1 — 카메라 스트리밍
python scripts/stream_camera.py --source csi --width 1280 --height 720

# 터미널 2 — 판단·구동 에이전트
python shepherdron_pi.py --fc /dev/ttyUSB0 --ground <노트북-IP> --altitude 10
```

### 지상 (노트북)

```bash
python shepherdron_ground.py \
    --source http://<pi-ip>:8000/stream.mjpg \
    --pi <pi-ip> \
    --calibration calibration/ground_plane.json
```

### 전부 로컬에서 검증 (하드웨어 없이)

```bash
python shepherdron_pi.py --fc udp:127.0.0.1:14550 --dry-run --ground 127.0.0.1 &
python shepherdron_ground.py --source 0 --pi 127.0.0.1
```

---

## 4. 포트

| 포트 | 방향 | 내용 |
|---|---|---|
| 8000 | 기체 → 지상 | MJPEG 영상 (HTTP) |
| 47600 | 지상 → 기체 | `VisionReport` — 관측 결과 (UDP) |
| 47601 | 기체 → 지상 | `TelemetryReport` — 상태 표시용 (UDP) |

UDP를 쓰는 이유: 이 링크는 **가장 최신 관측만** 의미가 있습니다. TCP는 끊긴 뒤 재연결하며
밀린 패킷을 순서대로 토해내는데, 그건 이미 지나간 군중 위치입니다.
오래된 보고로 기체를 움직이느니 아무것도 없는 편이 안전합니다.

---

## 5. 장애 시 동작

| 상황 | 결과 |
|---|---|
| 노트북 종료 / Wi-Fi 끊김 | 기체는 마지막 타겟까지 비행 → 90초 타임아웃 → RTL |
| 관측이 2초 이상 오래됨 | 없는 것으로 취급 (`Receiver.latest()` → `None`) |
| UDP 패킷 순서 뒤바뀜 | 순번이 역행한 패킷은 폐기 |
| 손상된 패킷 | 무시, 수신기는 계속 동작 |
| 고도 불명 | `has_ground_fix` False → 비행 명령 미발행 |
| 타겟이 반경 밖 | 같은 방위의 경계선으로 잘라냄 |
| **조종사 모드 전환** | **STANDBY — 비행 명령 일체 중단. 구조물만 수축** |
| Pixhawk heartbeat 끊김 | FAILSAFE → RTL |
| 배터리 부족 | FAILSAFE → RTL |

---

## 6. 대역폭

720p MJPEG q70 ≈ 20 FPS 기준 **약 8–15 Mbps**. 교내 시연 거리(50–100 m)에서 2.4 GHz로 충분합니다.
부족하면 `--quality`를 낮추거나 `--width 640 --height 480`으로 줄이세요.
관측·텔레메트리 UDP는 각각 **1 KB/s 미만**이라 무시해도 됩니다.

---

## 7. 카메라 마운트

**카메라는 45° 아래로 기울여 답니다.** 수직 하향은 사람이 어깨너비만 보여 10 m 고도에서
6.5 px이 되고, 발목 좌표 정의도 깨집니다. 근거는 [VISION.md](VISION.md) §2-4.

```
        기체
         │
         │  45°
         ▼ ↘
    ─────────────── 지면
      가까움  멂
      (하단)  (상단 — 검출 범위 벗어나면 UNKNOWN)
```

---

## 8. 남은 작업

- [ ] 45° 카메라 마운트 제작 및 실제 각도 실측
- [ ] 기체–지상 Wi-Fi 구성 확정 (Pi를 AP로 띄울지, 공유기를 쓸지)
- [ ] 실제 거리에서 MJPEG 지연·끊김 측정 ([#2](https://github.com/kennykimtang/shepherdron/issues/2))
- [ ] 조종기 개입 감지 → `mission.abort()` 연동
- [ ] `on_arrived`에 페이로드 연결 ([#8](https://github.com/kennykimtang/shepherdron/issues/8), [#10](https://github.com/kennykimtang/shepherdron/issues/10), [#11](https://github.com/kennykimtang/shepherdron/issues/11))
