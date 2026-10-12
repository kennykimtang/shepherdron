# 👁️ Shepherdron 비전 코어 (Phase 1)

> 군중 영상 → 인물 검출/추적 → **원근 보정 밀집도(persons/m²)** → 시간축 안정화 → **비행 타겟 좌표**

---

## 1. 파이프라인

```
 frame
   │
   ├─ PersonDetector.track()        YOLOv8n + ByteTrack, 동일 인물 ID 유지
   │     └─ foot-point = 박스 하단 중앙 (지상 접지점)
   │
   ├─ DensityAnalyzer.analyze()     N×M 그리드 + 지상 평면 투영
   │     └─ 셀별 persons/m²  (캘리브레이션 없으면 셀당 인원수로 대체)
   │
   ├─ AlertDebouncer                N-of-M 히스테리시스 + 최소 유지시간
   ├─ RollingCounter                인원수 중앙값 평활
   ├─ TargetSmoother                타겟 좌표 지수 평활
   │
   └─ CameraModel                   픽셀 → 방위각 → 기체 기준 전방/우측 오프셋(m)
```

`vision/pipeline.py`의 `CrowdPipeline` 한 클래스가 전부를 묶습니다. `main.py`는 입출력만 담당하므로,
Phase 2 비행 모듈과 라즈베리파이 실행기가 같은 파이프라인을 그대로 재사용합니다.

---

## 2. 이번에 해결한 설계 문제 3가지

### 2-1. 카운트가 떨려 드론 명령이 요동쳤다

프레임 단위 독립 검출만 했기 때문에, 한 사람이 잠깐 가려지거나 모션 블러가 끼면 인원수가 출렁이고
`is_overcrowded`가 즉시 뒤집혔습니다. 그 값이 그대로 비행 명령이 되면 드론이 경보마다 출발/회항을 반복합니다.

**해결**
- `PersonDetector.track()` — ByteTrack으로 프레임 간 동일 인물에 ID 유지
- `AlertDebouncer` — 최근 15프레임 중 60% 이상이어야 경보 ON, 25% 이하로 떨어져야 OFF,
  한번 켜지면 최소 5초 유지 (드론이 출발한 직후 꺼져 회항하는 것 방지)
- `RollingCounter` — 인원수 중앙값 평활. 한 프레임 폭주값에 둔감

```python
# tests/test_pipeline.py 에서 검증하는 동작
단발 스파이크 1프레임  →  raw_danger=True,  alert_active=False   # 경보로 올라가지 않음
지속적 과밀집          →  alert_active=True, rising_edge 정확히 1회
위험 해소 직후         →  min_on_s 동안 ON 유지
```

### 2-2. "밀집도"가 사실은 그냥 개수였다

기존 코드는 셀당 인원수로 판정했습니다. 그런데 카메라가 지면을 비스듬히 보므로
**화면 위쪽 셀(먼 지면)과 아래쪽 셀(가까운 지면)이 덮는 실제 면적이 다릅니다.**
보정 없이는 같은 "5명"이 어떤 셀에서는 여유롭고 어떤 셀에서는 압사 위험인데 구분할 수 없습니다.

**해결** — `vision/geometry.py`의 `GroundPlane` 호모그래피로 각 셀의 실제 지면 면적을 구해
`persons/m²`로 환산합니다.

| 밀집도 | 상태 |
|---|---|
| ~1.0 p/m² | 여유롭게 보행 가능 |
| **2.0 p/m²** | 보행 속도 저하, 접촉 시작 → `WARNING` |
| **4.0 p/m²** | 자력 이동 곤란 → `DANGER` |
| 5.0+ p/m² | 군중 압착(crowd crush) 위험 |

```
동일한 8명이 중앙 셀에 있을 때
  지면이 넓으면 (85 m²)  → 0.09 p/m²  → 정상
  지면이 좁으면 (0.85 m²) → 9.4  p/m²  → 위험
보정이 없으면 두 상황이 완전히 똑같아 보인다.
```

지평선 너머 셀은 면적이 정의되지 않으므로 `UNKNOWN`으로 표시하고 판정에서 제외합니다.

### 2-3. Phase 2로 넘길 좌표가 픽셀값이었다

`max_dense_cell.center`는 화면 좌표라 MAVLink가 쓸 수 없었습니다.

**해결** — `CameraModel`이 픽셀을 **기체 기준 지상 오프셋(미터)**으로 변환합니다.

```
   target pixel   : (103, 402)
   bearing offset : yaw -39.9°  pitch +24.1°
   ground offset  : forward -5.4 m, right -10.0 m  (AGL 12.0 m)
```

비행 모듈은 여기에 기체 yaw만 더하면 GPS 목표 좌표가 나옵니다.
타겟은 셀 중심이 아니라 **실제 발목 좌표의 무게중심**이라 더 정확합니다.

---

## 3. 사용법

### 3-1. 기본 실행

```bash
# 스마트폰 IP Webcam
python main.py --source http://192.168.0.25:8080/video

# 노트북 웹캠으로 먼저 확인
python main.py --source 0

# 녹화 클립으로 임계치 튜닝 (파일은 끝나면 자동 종료)
python main.py --source clip.mp4 --loop
```

### 3-2. 지상 평면 캘리브레이션 (밀집도를 m² 단위로 쓰려면 필수)

1. 촬영 지점 지면에 **사각형을 표시**합니다 — 바닥 테이프, 라바콘 4개, 주차구획선 무엇이든.
2. 가로/세로 실제 길이를 잽니다 (예: 6 m × 4 m).
3. 캘리브레이션 도구를 실행하고 네 모서리를 **좌상 → 우상 → 우하 → 좌하** 순서로 클릭합니다.

```bash
python scripts/calibrate_ground.py --source 0 --width 6.0 --height 4.0
# → calibration/ground_plane.json 생성
```

이후부터는 `main.py`가 자동으로 읽어 `persons/m²`로 판정합니다.

> 캘리브레이션은 **촬영 위치·카메라 각도마다 다시** 해야 합니다.
> 비행 중에는 고도를 알면 `ground_plane_from_altitude()`로 합성할 수 있지만,
> 지면이 평평하고 고도가 정확하다는 가정에 전적으로 의존합니다.

### 3-3. 비행 타겟 좌표 산출

```bash
python main.py --source csi --altitude 12 --pitch 90
```

`--altitude`(AGL, m)를 주면 경보 시 `forward_m` / `right_m`이 출력됩니다.
비행 중에는 코드에서 `pipeline.set_altitude(agl)`로 기압계 값을 계속 넣어 주세요.

### 3-4. 라즈베리파이 4 배포

Pi 4에서 PyTorch 원본 가중치로 640px 추론하면 **약 3 FPS**로 군중 추적에 쓸 수 없습니다.
NCNN으로 내보내고 320px로 낮추면 **8~10 FPS**가 나옵니다.

```bash
sudo apt install -y python3-picamera2 python3-libcamera
python -m venv --system-site-packages .venv    # picamera2 는 apt 패키지를 써야 한다
pip install -r requirements.txt -r requirements-pi.txt

python scripts/export_ncnn.py --imgsz 320      # yolov8n_ncnn_model/ 생성
./scripts/run_pi.sh                            # CSI 카메라 + NCNN 헤드리스 실행
```

히트싱크와 팬은 필수입니다. 무냉각으로 YOLO를 돌리면 수 분 내 서멀 쓰로틀링이 걸립니다.

---

## 4. 주요 CLI 옵션

| 옵션 | 설명 |
|---|---|
| `--source` | IP Webcam URL / 웹캠 번호 / 동영상 파일 / `csi` |
| `--model` `--imgsz` | 가중치(또는 NCNN 디렉터리)와 추론 입력 크기 |
| `--calibration` | 지상 평면 JSON 경로 |
| `--altitude` `--pitch` | AGL 고도(m), 카메라 하향각(도). 90 = 수직 하향 |
| `--density-danger` | 위험 밀집도 persons/m² (캘리브레이션 시) |
| `--danger` `--total-danger` | 셀당/전체 위험 인원수 (미캘리브레이션 시) |
| `--no-tracking` | ByteTrack 끄고 프레임 단위 검출만 |
| `--headless` | GUI 없이 실행 (라즈베리파이) |
| `--max-frames` `--loop` | 벤치마크용 프레임 제한 / 파일 반복 재생 |

**실행 중 단축키:** `q` 종료 · `s` 저장 · `g` 그리드 · `h` 히트맵 · `b` 박스 · `f` 발목점 · `r` 추적·필터 리셋

---

## 5. 테스트

모델 가중치를 내려받지 않고 순수 로직만 검증하므로 수 초 안에 끝납니다. CI에서 매 PR마다 돌아갑니다.

```bash
pytest tests/ -v
```

| 파일 | 검증 내용 |
|---|---|
| `test_geometry.py` | 호모그래피 정확도, 지평선 처리, 고도 비례, 화각↔초점거리 |
| `test_stability.py` | 스파이크 거부, 히스테리시스 갭, 최소 유지시간, 타겟 점프 전환 |
| `test_density_analyzer.py` | 원근 보정 유무에 따른 판정 차이, 셀 매핑, 타겟 무게중심 |
| `test_pipeline.py` | 경보 상승 에지 1회, 프레임 크기 동기화, 지상 오프셋 부호 |

---

## 6. 남은 작업

- [ ] **[AI-06]** 실제 군중 영상으로 `conf` / `iou` / 밀집도 임계치 현장 튜닝
- [ ] **[AI-07]** 라즈베리파이 CSI 실기 검증 (`PiCameraSource`는 구현 완료, 실기 미검증)
- [ ] **[AI-08]** Pi 4에서 NCNN 320px 실측 FPS 확인
- [ ] 원거리 소형 인물 검출률 — yolov8n으로 부족하면 yolov8s 또는 타일 추론 검토
- [ ] 야간/저조도 성능 — Camera Module 3 **NoIR** 버전 교체 여부 판단
