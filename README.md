# 🛰️ Shepherdron (하늘의 안내자) - 비전 인식 인구 밀집도 모듈

[![CI Pipeline](https://github.com/kennytang/shepherdron/actions/workflows/ci.yml/badge.svg)](https://github.com/kennytang/shepherdron/actions/workflows/ci.yml)
[![Project Status](https://img.shields.io/badge/Progress-40%25%20(Phase%201)-brightgreen)](file:///Users/kennytang/shepherdron/TASK_BOARD.md)
[![Python Version](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)

> **팀 작업 현황판 바로가기:**
> - 📋 **[실시간 작업 보드 (TASK_BOARD.md)](file:///Users/kennytang/shepherdron/TASK_BOARD.md)** : 현재 스프린트 작업 현황 & 담당자
> - 🗺️ **[프로젝트 개발 로드맵 (ROADMAP.md)](file:///Users/kennytang/shepherdron/ROADMAP.md)** : 4단계 마일스톤 및 간트 차트

스마트폰 카메라(IP Webcam) 및 향후 라즈베리파이 와이드 카메라와 연동하여, **YOLOv8 인물 검출**, **발목 좌표(Foot-point) 매핑**, **그리드 기반 군중 밀집도 히트맵 연산**, 그리고 **과밀집(Over-density) 판정**을 실시간으로 수행하는 비전 분석 코어 시스템입니다.

---

## 📁 프로젝트 구조

```text
shepherdron/
├── .github/                  # GitHub CI 파이프라인 및 Issue/PR 템플릿
│   ├── workflows/ci.yml      # 자동 테스트 CI 워크플로우
│   ├── ISSUE_TEMPLATE/       # 태스크 카드 및 버그 리포트 템플릿
│   └── pull_request_template.md
├── TASK_BOARD.md             # 📋 팀 실시간 작업 보드 (Kanban)
├── ROADMAP.md                # 🗺️ 4단계 마일스톤 및 일정 계획
├── config.py                 # 전역 설정 (IP Webcam URL, 임계치, 모델 파라미터)
├── vision/
│   ├── __init__.py
│   ├── detector.py           # YOLOv8 Person 검출 및 발목(Foot-point) 좌표 추출
│   ├── density_analyzer.py   # 그리드 분할, 밀집도 판정, 히트맵 시각화
│   └── stream_handler.py     # 저지연(Low-Latency) 멀티스레드 스트림 수신기
├── test_module.py            # 가상 군중 데이터를 통한 단위/통합 테스트 스크립트
├── main.py                   # 실시간 IP Webcam 스트림 분석 실행기
├── requirements.txt          # 필요 패키지 목록
└── .env.example              # 환경 변수 템플릿
```

---

## 📱 스마트폰(IP Webcam) 연결 및 사용 방법

### 1단계: 스마트폰 설정
1. 스마트폰과 컴퓨터가 **동일한 Wi-Fi 네트워크**에 연결되어 있는지 확인합니다.
2. 스마트폰에 **IP Webcam** (Android) 또는 **IP Camera** (iOS) 앱을 설치합니다.
3. 앱 실행 후 화면 하단의 **[Start server]** (또는 시작 버튼)를 누릅니다.
4. 스마트폰 화면에 표시된 스트림 주소를 확인합니다.
   - 예시: `http://192.168.0.25:8080` (영상 스트림 경로는 뒤에 `/video` 추가)
   - 최종 URL 형태: `http://192.168.0.25:8080/video`

### 2단계: 모듈 실행
가상환경(`source .venv/bin/activate`) 또는 직접 실행 바이너리를 통해 실행합니다:

```bash
# 기본 실행 (스마트폰 URL 지정)
./.venv/bin/python main.py --source http://192.168.0.25:8080/video

# 임계치(위험 인원수)를 조절하여 실행하고 싶은 경우
./.venv/bin/python main.py --source http://192.168.0.25:8080/video --danger 3 --total-danger 10
```

> 💡 **웹캠 테스트**: 만약 스마트폰 연결 전 노트북 내장 웹캠으로 먼저 테스트하고 싶다면:
> ```bash
> ./.venv/bin/python main.py --source 0
> ```

---

## ⌨️ 실시간 조작 단축키 (영상 모니터 창 활성화 시)

| 키 | 동작 |
|:---:|:---|
| **`q`** | 프로그램 안전 종료 |
| **`s`** | 현재 프레임 분석 화면을 `captures/` 폴더에 즉시 저장 |
| **`g`** | 그리드 격자선 On / Off 토글 |
| **`h`** | 반투명 밀집도 히트맵 On / Off 토글 |
| **`b`** | YOLO 인물 바운딩 박스 On / Off 토글 |
| **`f`** | 발목(Foot-point) 접지점 On / Off 토글 |

---

## 🧠 기술 구현 상세

1. **Foot-point (발목 좌표 매핑):**
   - 군중의 머리나 상체는 카메라 각도에 따라 원근 왜곡이 심하므로, 바운딩 박스의 하단 중앙 `((x1+x2)/2, y2)`을 지상 접지점으로 사용하여 실제 위치를 추정합니다.
2. **그리드 분할 & 과밀집 탐지:**
   - 화면을 $N \times M$ 그리드로 분할하여 특정 구역의 밀집 인원수가 임계치(`grid_danger_threshold`)를 초과하거나 전체 인원이 `total_danger_threshold`를 넘을 시 즉시 `OVER-DENSITY ALERT`를 트리거합니다.
   - 가장 혼잡한 구역의 중심점(Target Crosshair)을 추적하여 향후 드론의 목표 좌표로 전송할 수 있도록 준비되어 있습니다.
3. **저지연 멀티스레드 스트리밍:**
   - OpenCV 기본 버퍼링으로 인해 발생하는 스트림 딜레이를 방지하기 위해 백그라운드 캡처 스레드를 통해 항상 0초 딜레이의 최신 프레임을 획득합니다.
