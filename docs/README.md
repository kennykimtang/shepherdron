Shepherdron 웹 시연판

https://kennykimtang.github.io/shepherdron/

브라우저에서 군중 밀집도 인식과 드론 유도 판단을 그대로 돌립니다.
설치가 필요 없어 발표장 PC 에서 링크만 열면 됩니다.

| 파일 | 내용 |
|---|---|
| `vision.js` | KDE 밀집도 · ROI 면적 · 등급 · 전술 투영 · 유도 방향 · 임무 상태기계 |
| `detector.js` | YOLOv8n 사람 검출 (onnxruntime-web, WebGPU → WASM) |
| `link.js` | 폰 ↔ PC WebRTC 연결 · QR |
| `app.js` | 화면 그리기 · 조작 |
| `yolov8n.onnx` | 노트북 파이썬판과 같은 가중치 (12 MB) |

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

검출도 같은 YOLOv8n 가중치입니다. `scripts/export_web_model.py` 로
ONNX 를 다시 내보낼 수 있습니다. 전처리·후처리는 ultralytics 결과와
대조해 맞췄습니다 (bus.jpg 양쪽 4명, IoU 0.90~0.98, 좌표 오차 1.6~12 px).

운용 절차는 [DEMO.md](../DEMO.md) 를 보세요.
