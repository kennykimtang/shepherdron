#!/usr/bin/env python3
"""웹 시연판용 YOLOv8n ONNX 내보내기.

docs/ 의 웹판은 노트북과 같은 가중치를 써야 결과가 어긋나지 않는다.
모델을 바꾸면 이 스크립트로 다시 내보낸다.

    python scripts/export_web_model.py
    python scripts/export_web_model.py --model yolov8s.pt   # 더 정확, 더 느림

내보낸 뒤 docs/detector.js 의 INPUT 과 입력 크기가 같은지 확인할 것.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description="웹판 ONNX 모델 내보내기")
    ap.add_argument("--model", default="yolov8n.pt")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--out", default="docs/yolov8n.onnx")
    args = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics 가 필요합니다: pip install ultralytics", file=sys.stderr)
        return 1

    print(f"[export] {args.model} → ONNX (imgsz={args.imgsz})")
    path = YOLO(args.model).export(format="onnx", imgsz=args.imgsz, opset=12,
                                   simplify=True, dynamic=False, nms=False)
    dst = ROOT / args.out
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), dst)
    mb = dst.stat().st_size / 1e6
    print(f"[export] 완료 — {dst} ({mb:.1f} MB)")
    print("[export] docs/detector.js 의 INPUT 이 "
          f"{args.imgsz} 인지 확인하세요.")
    print("[export] .gitignore 가 *.onnx 를 무시하므로 "
          "docs/*.onnx 예외가 살아 있어야 합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
