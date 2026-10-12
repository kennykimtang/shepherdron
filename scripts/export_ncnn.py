#!/usr/bin/env python3
"""YOLOv8n 을 NCNN 으로 내보낸다 — 라즈베리파이 4 추론 가속용.

Pi 4 에서 PyTorch 원본 가중치로 640px 추론하면 약 3 FPS 로 군중 추적에
쓸 수 없다. NCNN 으로 내보내고 입력을 320px 로 낮추면 8~10 FPS 가 나온다.

사용법
    python scripts/export_ncnn.py                 # yolov8n.pt, imgsz 320
    python scripts/export_ncnn.py --imgsz 416
결과물
    yolov8n_ncnn_model/   ← 이 디렉터리 경로를 YOLO_MODEL 에 지정
"""
import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Export YOLO weights to NCNN for Raspberry Pi")
    ap.add_argument("--weights", default="yolov8n.pt", help="source .pt weights")
    ap.add_argument("--imgsz", type=int, default=320,
                    help="inference size; 320 is the Pi 4 sweet spot")
    ap.add_argument("--half", action="store_true", help="fp16 (ARM 에서는 보통 효과 없음)")
    args = ap.parse_args()

    if not Path(args.weights).exists():
        print(f"[export] weights not found: {args.weights}", file=sys.stderr)
        return 1

    from ultralytics import YOLO

    print(f"[export] loading {args.weights}")
    model = YOLO(args.weights)
    print(f"[export] exporting to NCNN at imgsz={args.imgsz} …")
    out = model.export(format="ncnn", imgsz=args.imgsz, half=args.half)
    print(f"[export] done -> {out}")
    print()
    print("라즈베리파이 .env 설정:")
    print(f"  YOLO_MODEL={out}")
    print(f"  YOLO_IMGSZ={args.imgsz}")
    print( "  YOLO_DEVICE=cpu")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
