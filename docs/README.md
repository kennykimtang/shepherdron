Shepherdron 웹 시연판

https://kennykimtang.github.io/shepherdron/

브라우저에서 군중 밀집도 인식과 드론 유도 판단을 그대로 돌립니다.
설치가 필요 없어 발표장 PC 에서 링크만 열면 됩니다.

| 파일 | 내용 |
|---|---|
| `vision.js` | KDE 밀집도 · ROI 면적 · 등급 · 전술 투영 · 유도 방향 · 임무 상태기계 |
| `app.js` | 카메라 · 검출(coco-ssd) · 화면 그리기 |

`vision.js` 는 저장소의 `vision/density_field.py`, `vision/tactical.py`,
`flight/mission.py` 를 옮긴 것입니다. 같은 수식을 써야 노트북 결과와
브라우저 결과가 어긋나지 않습니다. 브라우저 API 를 쓰지 않으므로
node 로 검증할 수 있습니다.

검출 모델만 다릅니다. 웹은 coco-ssd, 노트북은 YOLOv8n 입니다.
사람 박스를 내는 역할은 같고 그 뒤 판단은 전부 같습니다.

운용 절차는 [DEMO.md](../DEMO.md) 를 보세요.
