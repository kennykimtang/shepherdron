# 📋 Shepherdron 실시간 작업 보드 (Task Board)

> **프로젝트 목표:** YOLO 군중 비전 인식 + 픽스호크 MAVLink 자율비행 + 기구 전개(액추에이터/LED/스피커) 통합 시스템  
> **최근 업데이트:** 2026-10-12  
> **전체 진행률:** `[█████░░░░░] 50%` (Phase 1 비전 코어 완료 · 현장 튜닝 남음)

---

## 🚦 실시간 칸반 상태판 (Kanban Overview)

| 📌 Backlog (할 일) | ⚙️ In Progress (진행 중) | 🔍 Review / Test (검증 중) | ✅ Done (완료) |
|---|---|---|---|
| [NAV] Waypoint 순찰 경로 생성 | [AI] 임계치 현장 튜닝 | [AI] 발목(Foot-point) 매핑 정확도 | [INIT] 프로젝트 구조 설계 |
| [HW] DMD-150 모터드라이버 배선 | [DOC] 팀 프로젝트 README 및 가이드 | [AI] 3x3 그리드 밀집도 연산 로직 | [AI] YOLOv8n 모델 로더 및 MPS 가속 |
| [HW] WS2812B LED 점등 패턴 구현 | | | [AI] 저지연 멀티스레드 스트림 처리기 |
| [NAV] MAVLink 이륙 및 호버링 제어 | | | [TEST] 가상 군중 밀집도 시각화 검증 |
| [SYS] 라즈베리파이 4 OS 환경 세팅 | | | [CI] GitHub Actions 자동 빌드 파이프라인 |

---

## 👥 파트별 상세 태스크 및 담당자

### 👁️ Part 1: AI 비전 인식 (Vision & Density)
- [x] **[AI-01]** YOLOv8 기반 `Person` 클래스 필터링 및 추론 파이프라인 구축
- [x] **[AI-02]** 지상 접지점 추정을 위한 Foot-point (발목 좌표: $(x_1+x_2)/2, y_2$) 연산 모듈
- [x] **[AI-03]** $N \times M$ 그리드 분할 및 셀별 밀집도/과밀집(Over-density) 판정 알고리즘
- [x] **[AI-04]** 반투명 히트맵 및 HUD(FPS, 인원수, 경보 배너) 시각화 렌더러
- [x] **[AI-05]** 스마트폰 IP Webcam 스트림 저지연 버퍼링 제어기 (`StreamHandler`)
- [x] **[AI-06a]** ByteTrack 추적 연동 — 프레임 간 동일 인물 ID 유지로 카운트 흔들림 제거
- [x] **[AI-06b]** 경보 히스테리시스 (N-of-M + 최소 유지시간) — 단발 스파이크가 비행 명령이 되지 않도록
- [x] **[AI-06c]** 원근 보정 밀집도 (persons/m²) + 지상 평면 캘리브레이션 도구
- [x] **[AI-06d]** 타겟 좌표 미터 환산 (픽셀 → 방위각 → 기체 기준 전방/우측 오프셋)
- [ ] **[AI-06e]** 실제 군중 영상으로 `conf`/`iou`/밀집도 임계치 현장 튜닝
- [ ] **[AI-07]** 라즈베리파이 카메라 모듈 3 와이드 (CSI/libcamera) 파이프라인 연동
- [x] **[AI-08a]** NCNN export 스크립트 + Pi 실행기 작성
- [ ] **[AI-08b]** Pi 4 실기에서 NCNN 320px 실측 FPS 확인

### 🚁 Part 2: 자율비행 및 항법 제어 (Flight & Navigation)
- [ ] **[NAV-01]** DroneKit-Python 환경 세팅 및 SITL(가상 시뮬레이터) 연결 테스트
- [ ] **[NAV-02]** 픽스호크(KOA FC) UART Serial 통신 연결 (`/dev/ttyAMA0`, 921600 baud)
- [ ] **[NAV-03]** 비행 모드 전환 함수 구현 (`GUIDED` 모드 진입 및 안전 페일세이프)
- [ ] **[NAV-04]** 과밀집 타겟 셀 기반 상대 GPS 좌표 변환 및 `simple_goto` 비행 함수 구현
- [ ] **[NAV-05]** 목표 고도(10m) 도달 판정 및 정밀 호버링 시퀀스

### ⚙️ Part 3: 기구부 및 전장 하드웨어 (Hardware & Actuator)
- [ ] **[HW-01]** **3S 11.1V** LiPo 배터리 및 5V/5A UBEC 클린 전원 분배 회로 설계/체결 (4S 아님 — [근거](HARDWARE_SPEC.md))
- [ ] **[HW-02]** LMB2036U 리니어 액추에이터 제어 (**GPIO 13 PWM1 + GPIO 6 DIR**, 74AHCT125 경유)
- [ ] **[HW-03]** 크레슬링 오리가미 구조물 전개 테스트 (**스트로크 150mm 상한** · 구조물 질량 **150g 이하**)
- [ ] **[HW-04]** WS2812B 30LED 방향 지시 점등 패턴 (**GPIO 10 SPI0**, 밝기 50% 상한)
- [ ] **[HW-05]** MAX98357A I2S 앰프 + 스피커 경고 음성 출력 연동 (GPIO 18/19/21)
- [ ] **[HW-06]** 배터리 3S 3300mAh 교체 검토 (2200mAh 기준 체공 5.3분 → 7.7분)
- [x] **[HW-00]** 하드웨어 스펙 검증 및 배선도 rev.B 확정 ([HARDWARE_SPEC.md](HARDWARE_SPEC.md))

### 📄 Part 4: 통합 및 문서/발표 (System & Documentation)
- [x] **[SYS-01]** GitHub 협업 환경 (CI, Issue/PR 템플릿, 로드맵) 구축
- [ ] **[SYS-02]** 전체 통합 실행 스크립트 (`shepherdron_core.py`) 릴리즈
- [ ] **[DOC-01]** 전체 시스템 아키텍처 다이어그램 및 시연 시나리오 작성
- [ ] **[DOC-02]** 최종 발표용 PPT 슬라이드 및 시연 영상 촬영

---

## 🔄 작업 업데이트 규칙 (팀원 공유용)
1. **작업 시작 전:** 담당할 태스크의 체크박스를 확인하고 GitHub Issue 또는 브랜치를 생성합니다 (`feat/<파트>-<작업명>`).
2. **작업 진행 중:** 위 표의 `In Progress` 영역에 본인 ID와 함께 등록합니다.
3. **PR 생성 시:** 본문 내용에 `Resolves #[이슈번호]`를 기재하여 PR 머지 시 자동으로 태스크가 완료되도록 합니다.
4. **테스트 필수:** 코드를 푸시하기 전 `./.venv/bin/python test_module.py`가 정상 통과하는지 확인합니다.
