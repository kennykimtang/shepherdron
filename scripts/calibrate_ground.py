#!/usr/bin/env python3
"""지상 평면 캘리브레이션 — 밀집도를 persons/m^2 로 환산하기 위한 1회 작업.

왜 필요한가
    카메라가 지면을 비스듬히 보므로 화면 위쪽 셀과 아래쪽 셀이 덮는
    실제 지면 넓이가 다르다. 보정 없이는 "셀당 5명"이 어떤 셀에서는
    여유롭고 어떤 셀에서는 압사 위험인데 둘을 구분할 수 없다.

절차
    1. 촬영 위치에서 지면에 직사각형을 표시한다 (예: 4 m x 3 m).
       바닥 테이프, 라바콘 4개, 주차구획선 등 무엇이든 좋다.
    2. 그 장면을 이 스크립트로 띄운다.
    3. 사각형 네 모서리를 좌상 → 우상 → 우하 → 좌하 순서로 클릭한다.
    4. 실제 가로/세로 길이(m)를 입력하면 calibration/ground_plane.json 이 생성된다.

사용법
    python scripts/calibrate_ground.py --source 0
    python scripts/calibrate_ground.py --source http://192.168.0.10:8080/video
    python scripts/calibrate_ground.py --image frame.jpg --width 4.0 --height 3.0
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vision.geometry import GroundPlane  # noqa: E402

WINDOW = "Shepherdron ground-plane calibration"
ORDER = ["top-left", "top-right", "bottom-right", "bottom-left"]


def grab_frame(args) -> np.ndarray:
    if args.image:
        frame = cv2.imread(args.image)
        if frame is None:
            raise SystemExit(f"이미지를 열 수 없습니다: {args.image}")
        return frame

    src = int(args.source) if str(args.source).isdigit() else args.source
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit(f"스트림을 열 수 없습니다: {args.source}")
    print("[calib] 스페이스로 프레임 고정, q 로 종료")
    frame = None
    while True:
        ok, f = cap.read()
        if not ok:
            continue
        cv2.imshow(WINDOW, f)
        k = cv2.waitKey(1) & 0xFF
        if k == ord(" "):
            frame = f.copy()
            break
        if k == ord("q"):
            cap.release()
            cv2.destroyAllWindows()
            raise SystemExit("사용자 취소")
    cap.release()
    return frame


def pick_points(frame: np.ndarray) -> list:
    pts: list = []

    def draw() -> np.ndarray:
        vis = frame.copy()
        for i, (x, y) in enumerate(pts):
            cv2.circle(vis, (x, y), 7, (0, 0, 255), -1)
            cv2.putText(vis, f"{i+1} {ORDER[i]}", (x + 12, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
        if len(pts) > 1:
            cv2.polylines(vis, [np.array(pts, np.int32)], len(pts) == 4,
                          (0, 255, 0), 2)
        nxt = ORDER[len(pts)] if len(pts) < 4 else "완료 — ENTER 로 확정, u 로 취소"
        cv2.rectangle(vis, (0, 0), (vis.shape[1], 40), (0, 0, 0), -1)
        cv2.putText(vis, f"click: {nxt}", (14, 27),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        return vis

    def on_mouse(event, x, y, flags, _):
        if event == cv2.EVENT_LBUTTONDOWN and len(pts) < 4:
            pts.append((x, y))
            cv2.imshow(WINDOW, draw())

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(WINDOW, on_mouse)
    cv2.imshow(WINDOW, draw())

    while True:
        k = cv2.waitKey(20) & 0xFF
        if k == ord("u") and pts:
            pts.pop()
            cv2.imshow(WINDOW, draw())
        elif k in (13, 10) and len(pts) == 4:
            break
        elif k == ord("q"):
            cv2.destroyAllWindows()
            raise SystemExit("사용자 취소")
    cv2.destroyAllWindows()
    return pts


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrate the image-to-ground homography")
    ap.add_argument("--source", default="0", help="webcam index / IP Webcam URL / video file")
    ap.add_argument("--image", help="대신 정지 이미지 파일을 쓴다")
    ap.add_argument("--width", type=float, help="표시한 사각형의 실제 가로 길이 (m)")
    ap.add_argument("--height", type=float, help="표시한 사각형의 실제 세로 길이 (m)")
    ap.add_argument("--out", default="calibration/ground_plane.json")
    ap.add_argument("--label", default="", help="촬영 장소 메모")
    args = ap.parse_args()

    frame = grab_frame(args)
    print(f"[calib] frame {frame.shape[1]}x{frame.shape[0]}")
    img_pts = pick_points(frame)

    w = args.width if args.width else float(input("사각형 실제 가로 길이 (m): "))
    h = args.height if args.height else float(input("사각형 실제 세로 길이 (m): "))
    if w <= 0 or h <= 0:
        raise SystemExit("길이는 0보다 커야 합니다.")

    # 지상 좌표계: X 우측, Y 전방(카메라에서 멀어지는 방향), 원점은 좌하단 모서리
    world_pts = [(0.0, h), (w, h), (w, 0.0), (0.0, 0.0)]

    plane = GroundPlane.from_points(img_pts, world_pts, label=args.label or args.source)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    plane.save(args.out)

    full = plane.polygon_area_m2([(0, 0), (frame.shape[1], 0),
                                  (frame.shape[1], frame.shape[0]),
                                  (0, frame.shape[0])])
    print(f"[calib] saved -> {args.out}")
    print(f"[calib] 기준 사각형 실측 면적 {w * h:.2f} m^2")
    if full:
        print(f"[calib] 화면 전체 지면 면적 약 {full:.1f} m^2")
    else:
        print("[calib] 화면 상단이 지평선 너머입니다 — 해당 셀은 UNKNOWN 으로 표시됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
