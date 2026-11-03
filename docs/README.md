Shepherdron 웹 시연판

https://kennykimtang.github.io/shepherdron/

브라우저에서 군중 밀집도 인식과 드론 유도 판단을 그대로 돌립니다.
설치가 필요 없어 발표장 PC 에서 링크만 열면 됩니다.

| 파일 | 내용 |
|---|---|
| `vision.js` | KDE 밀집도 · ROI 면적 · 등급 · 전술 투영 · 유도 방향 · 임무 상태기계 |
| `detector.js` | 머리 검출 · 타일 분할 추론 (onnxruntime-web, WebGPU → WASM) |
| `link.js` | 폰 ↔ PC WebRTC 연결 · QR |
| `app.js` | 화면 그리기 · 조작 |
| `head.onnx` | CrowdHuman person+head YOLOv11s 가중치 (38 MB) |

쓰는 방법 세 가지

| 모드 | 쓸 곳 |
|---|---|
| 폰 카메라 연결 | 발표장 PC 가 화면, 폰이 카메라. QR 을 찍으면 붙는다 |
| 이 기기 카메라 | 한 기기에서 전부 |
| 영상 파일 | 녹화본으로 같은 처리 |

`vision.js` 는 저장소의 `vision/density_field.py`, `vision/tactical.py`,
`flight/mission.py` 를 옮긴 것입니다. 같은 수식을 써야 노트북 결과와
브라우저 결과가 어긋나지 않습니다. 브라우저 API 를 쓰지 않으므로
node 로 검증할 수 있습니다.

검출은 머리를 봅니다. COCO 로 학습한 yolov8n 의 person 은 전신 박스를
기대하고 배운 탓에, 몸통이 앞사람에 가린 군중에서 거의 못 잡습니다.
마라톤 출발선 사진(2589x1458, 300명 이상)으로 재 보니 앞줄 4명이
전부였습니다. 군중에서 끝까지 보이는 건 머리뿐이라 CrowdHuman 으로 학습한
person+head 모델(huggingface.co/Sharath33/Person, openrail++)의 head
클래스로 바꿨습니다. 같은 사진 같은 조건에서 136명이 나옵니다.

멀리 있는 사람까지 봐야 할 때는 화면을 NxN 으로 쪼개 조각마다 추론을
돌립니다(툴바 분할, 단축키 `t`). 조각이 맡는 넓이가 1/N² 이라 같은 사람이
N 배 크게 들어갑니다. 머리 모델에서는 분할 없이도 충분해 기본은 꺼 둡니다.

축척(m/px)은 머리 세로를 0.23 m 로 두고 역산합니다. 촬영 구역의 실제 넓이를
툴바에 넣으면 그 값으로 바로 환산하므로 더 정확합니다.

운용 절차는 [DEMO.md](../DEMO.md) 를 보세요.
