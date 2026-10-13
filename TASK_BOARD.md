# 📋 Shepherdron 작업 보드

> **진행률:** `[█████░░░░░] 50%` — Phase 1 비전 코어 완료, 현장 튜닝 남음
> **최근 업데이트:** 2026-10-12

이 파일은 **큰 그림**입니다. 실제 작업 추적은 GitHub에서 합니다.

| 용도 | 위치 |
|---|---|
| 🗂️ **작업 추적 (칸반)** | [GitHub Issues](https://github.com/kennykimtang/shepherdron/issues) |
| 🏁 **단계별 마감** | [Milestones](https://github.com/kennykimtang/shepherdron/milestones) |
| ✅ **CI 상태** | [Actions](https://github.com/kennykimtang/shepherdron/actions) |

---

## 🚦 현재 상태

| 파트 | 상태 | 다음 할 일 |
|---|---|---|
| 👁️ **비전** | 코어 완료 | 실기 검증 3건 — [#1](https://github.com/kennykimtang/shepherdron/issues/1) [#2](https://github.com/kennykimtang/shepherdron/issues/2) [#3](https://github.com/kennykimtang/shepherdron/issues/3) |
| 🚁 **항법** | 미착수 | SITL 환경 구성부터 — [#4](https://github.com/kennykimtang/shepherdron/issues/4) |
| ⚙️ **하드웨어** | 설계 검증 완료 | 전원 배선부터 — [#7](https://github.com/kennykimtang/shepherdron/issues/7) |
| 📄 **문서** | 설계 문서 완료 | 발표 자료 — [#14](https://github.com/kennykimtang/shepherdron/issues/14) |

---

## ✅ 완료

### 👁️ 비전 인식 (Phase 1)
- [x] YOLOv8n Person 검출 + Foot-point 지상 접지점 연산
- [x] N×M 그리드 분할 및 셀별 밀집도 판정
- [x] 저지연 멀티스레드 스트림 수신기
- [x] **ByteTrack 추적 연동** — 프레임 간 동일 인물 ID 유지로 카운트 흔들림 제거
- [x] **경보 히스테리시스** — 단발 스파이크가 비행 명령이 되지 않도록 N-of-M + 최소 유지시간
- [x] **원근 보정 밀집도 (persons/m²)** + 지상 평면 캘리브레이션 도구
- [x] **타겟 좌표 미터 환산** — 픽셀 → 방위각 → 기체 기준 전방/우측 오프셋
- [x] 라즈베리파이 CSI 백엔드 및 NCNN 내보내기 스크립트
- [x] pytest 62건 (모델 가중치 없이 수초 내 완료) + CI 연동

### ⚙️ 하드웨어 (설계)
- [x] 부품 스펙 검증 — rev.A 설계 오류 **9건 교정** ([HARDWARE_SPEC.md](HARDWARE_SPEC.md))
- [x] 질량·추력·체공·전원 예산 산출
- [x] 결선도 및 배선 명세 ([WIRING.md](WIRING.md))

### 🔧 인프라
- [x] GitHub 레포, Issues, Milestones, 라벨 체계
- [x] CI 파이프라인 (pytest + import 검증)

---

## 📌 진행 중 / 대기

전체 목록은 [Issues](https://github.com/kennykimtang/shepherdron/issues)를 보세요.

| # | 작업 | 파트 | 우선순위 |
|---|---|---|---|
| [#1](https://github.com/kennykimtang/shepherdron/issues/1) | 군중 영상으로 탐지·밀집도 임계치 현장 튜닝 | 비전 | 높음 |
| [#2](https://github.com/kennykimtang/shepherdron/issues/2) | 라즈베리파이 CSI 카메라 실기 검증 | 비전 | 높음 |
| [#3](https://github.com/kennykimtang/shepherdron/issues/3) | Pi 4 NCNN 320px 실측 FPS 확인 | 비전 | 높음 |
| [#4](https://github.com/kennykimtang/shepherdron/issues/4) | SITL 환경 구성 및 연결 | 항법 | 높음 |
| [#5](https://github.com/kennykimtang/shepherdron/issues/5) | Pixhawk TELEM2 시리얼 통신 확립 | 항법 | 높음 |
| [#6](https://github.com/kennykimtang/shepherdron/issues/6) | 타겟 오프셋 → GPS 변환 및 simple_goto | 항법 | 높음 |
| [#7](https://github.com/kennykimtang/shepherdron/issues/7) | 3S 전원 분배 회로 구축 | 하드웨어 | 높음 |
| [#8](https://github.com/kennykimtang/shepherdron/issues/8) | 액추에이터 제어 (GPIO13 + GPIO6) | 하드웨어 | 높음 |
| [#9](https://github.com/kennykimtang/shepherdron/issues/9) | 오리가미 구조물 전개 테스트 | 하드웨어 | 보통 |
| [#10](https://github.com/kennykimtang/shepherdron/issues/10) | WS2812B LED 방향 지시 패턴 | 하드웨어 | 보통 |
| [#11](https://github.com/kennykimtang/shepherdron/issues/11) | MAX98357A 음성 경보 | 하드웨어 | 보통 |
| [#12](https://github.com/kennykimtang/shepherdron/issues/12) | 배터리 3300 mAh 교체 검토 | 하드웨어 | 높음 |
| [#13](https://github.com/kennykimtang/shepherdron/issues/13) | 통합 실행 스크립트 | 인프라 | 보통 |
| [#14](https://github.com/kennykimtang/shepherdron/issues/14) | 발표 자료 및 시연 영상 | 문서 | 보통 |

---

## 🏗️ 확정된 구조 결정 (2026-10-13)

**비전 연산은 지상 노트북, 판단과 구동은 기체.** 근거와 장애 동작은 [ARCHITECTURE.md](ARCHITECTURE.md).

- 노트북이 YOLO를 돌리고 **관측 결과만** 전송 (비행 명령은 링크로 안 나감)
- 상태기계·페일세이프는 기체에 — Wi-Fi 끊겨도 마지막 타겟까지 간 뒤 자동 RTL
- 픽셀을 보내고 고도를 아는 기체가 미터로 환산

---

## ⚠️ 팀 결정이 필요한 사항

1. **목표 체공시간** — 현재 2200 mAh 기준 **5.3분**. 이 값이 배터리 용량과 페이로드 상한을 역으로 결정합니다. ([#12](https://github.com/kennykimtang/shepherdron/issues/12))
2. **오리가미 전개 변위** — LMB2036U 스트로크 상한이 **150 mm**. 더 필요하면 링크 증폭이나 2단 직렬이 필요합니다. ([#9](https://github.com/kennykimtang/shepherdron/issues/9))
3. **구조물 질량** — **150 g 초과 시** 추력중량비가 1.6 아래로 떨어져 비행 안정성이 나빠집니다.

---

## 🔄 작업 규칙

1. **시작 전** — Issue를 자신에게 할당하고 `feat/<파트>-<작업>` 브랜치를 만듭니다.
2. **PR** — 본문에 `Resolves #<번호>`를 적으면 머지 시 Issue가 자동으로 닫힙니다.
3. **테스트** — 푸시 전 `pytest tests/` 통과 확인. CI가 모든 PR에서 다시 돌립니다.
4. **main 직접 푸시 금지** — 반드시 PR로 올립니다.
