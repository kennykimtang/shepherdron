#!/usr/bin/env bash
# 라즈베리파이 4 온보드 실행 — CSI 카메라 + NCNN 320px, 헤드리스
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${YOLO_MODEL:-yolov8n_ncnn_model}"
if [[ ! -d "$MODEL" ]]; then
  echo "NCNN 모델이 없습니다: $MODEL"
  echo "먼저 실행하세요:  python scripts/export_ncnn.py --imgsz 320"
  exit 1
fi

exec python main.py \
  --source csi \
  --model "$MODEL" \
  --imgsz "${YOLO_IMGSZ:-320}" \
  --headless \
  "$@"
