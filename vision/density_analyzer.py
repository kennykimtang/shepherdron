"""그리드 밀집도 분석 — 원근 보정된 persons/m^2 를 산출한다.

캘리브레이션(GroundPlane)이 주어지면 각 셀이 덮는 실제 지면 면적을 구해
밀집도를 m^2 당 인원으로 환산한다. 캘리브레이션이 없으면 예전처럼
셀당 인원수로 판정하되, 결과에 calibrated=False 를 표시해 두어
"이 수치는 원근 보정이 안 된 값"임을 호출 측이 알 수 있게 한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from vision.detector import DetectionResult
from vision.geometry import CameraModel, GroundPlane

# 군중 밀집도 기준 (persons/m^2). G.K. Still 등 군중안전 문헌의 통용 구간.
#   ~1.0  여유롭게 보행 가능
#   ~2.0  보행 속도 저하, 접촉 시작
#   ~4.0  자력 이동 곤란
#   5.0+  군중 압착(crowd crush) 위험
DEFAULT_DENSITY_WARN = 2.0
DEFAULT_DENSITY_DANGER = 4.0


@dataclass
class GridCell:
    row: int
    col: int
    x1: int
    y1: int
    x2: int
    y2: int
    count: int = 0
    status: str = "EMPTY"                   # EMPTY / NORMAL / WARNING / DANGER / UNKNOWN
    area_m2: Optional[float] = None         # 이 셀이 덮는 실제 지면 면적
    density: Optional[float] = None         # persons / m^2
    track_ids: List[int] = field(default_factory=list)
    slant_range_m: Optional[float] = None   # 카메라에서 이 셀까지 직선 거리
    in_detection_range: bool = True         # 사람을 볼 수 있는 거리인가

    @property
    def center(self) -> Tuple[int, int]:
        return (int((self.x1 + self.x2) / 2), int((self.y1 + self.y2) / 2))

    @property
    def corners(self) -> List[Tuple[float, float]]:
        return [(self.x1, self.y1), (self.x2, self.y1), (self.x2, self.y2), (self.x1, self.y2)]

    @property
    def reliable(self) -> bool:
        """면적을 신뢰할 수 있는가. 지평선 너머 셀은 False."""
        return self.area_m2 is not None and self.area_m2 > 0


@dataclass
class DensityAnalysisResult:
    total_persons: int
    grid_cells: List[GridCell] = field(default_factory=list)
    max_dense_cell: Optional[GridCell] = None
    is_overcrowded: bool = False
    alarm_reasons: List[str] = field(default_factory=list)

    calibrated: bool = False                 # 지상 평면 캘리브레이션 적용 여부
    peak_density: Optional[float] = None     # 최대 셀의 persons/m^2
    target_point: Optional[Tuple[int, int]] = None   # 타겟 화면 좌표(발목 무게중심)

    @property
    def metric(self) -> str:
        return "persons/m^2" if self.calibrated else "persons/cell"


class DensityAnalyzer:
    """프레임을 그리드로 나누고 Foot-point 를 지면에 투영해 밀집도를 판정한다."""

    def __init__(
        self,
        grid_rows: int = 3,
        grid_cols: int = 3,
        warn_threshold: int = 3,
        danger_threshold: int = 5,
        total_threshold: int = 15,
        heatmap_alpha: float = 0.35,
        ground_plane: Optional[GroundPlane] = None,
        density_warn: float = DEFAULT_DENSITY_WARN,
        density_danger: float = DEFAULT_DENSITY_DANGER,
        min_cell_area_m2: float = 0.5,
        camera: Optional[CameraModel] = None,
    ):
        self.rows = grid_rows
        self.cols = grid_cols
        self.warn_threshold = warn_threshold
        self.danger_threshold = danger_threshold
        self.total_threshold = total_threshold
        self.heatmap_alpha = heatmap_alpha

        self.ground_plane = ground_plane
        self.density_warn = density_warn
        self.density_danger = density_danger
        # 너무 작은 면적은 0으로 나누기에 가까워 밀집도가 폭주한다. 하한을 둔다.
        self.min_cell_area_m2 = min_cell_area_m2

        # 카메라를 주면 셀마다 "거기까지 보이는가"를 판단한다.
        # 비스듬히 보면 화면 위쪽 셀은 수십 미터 밖이라 사람이 몇 픽셀밖에 안 된다.
        # 그 구역의 "검출 0명"은 "사람이 없다"가 아니라 "보이지 않는다"이므로,
        # 밀집도 0(=안전)으로 보고하면 거짓 음성이 된다.
        self.camera = camera

        self._area_cache: Dict[Tuple[int, int, int, int], Optional[float]] = {}

    # ─────────────────────── 캘리브레이션 ───────────────────────
    def set_ground_plane(self, plane: Optional[GroundPlane]) -> None:
        self.ground_plane = plane
        self._area_cache.clear()

    @property
    def calibrated(self) -> bool:
        return self.ground_plane is not None and self.ground_plane.is_calibrated()

    def _cell_area(self, cell: GridCell, frame_shape: Tuple[int, ...]) -> Optional[float]:
        if not self.calibrated:
            return None
        key = (cell.x1, cell.y1, cell.x2, cell.y2)
        if key not in self._area_cache:
            assert self.ground_plane is not None
            self._area_cache[key] = self.ground_plane.polygon_area_m2(cell.corners)
        return self._area_cache[key]

    # ─────────────────────────── 분석 ───────────────────────────
    def analyze(
        self,
        frame_shape: Tuple[int, ...],
        detection: DetectionResult,
        altitude_m: Optional[float] = None,
    ) -> DensityAnalysisResult:
        height, width = frame_shape[:2]
        cell_w = width / self.cols
        cell_h = height / self.rows

        # 1. 그리드 생성
        grid: Dict[Tuple[int, int], GridCell] = {}
        for r in range(self.rows):
            for c in range(self.cols):
                grid[(r, c)] = GridCell(
                    row=r, col=c,
                    x1=int(c * cell_w), y1=int(r * cell_h),
                    x2=int((c + 1) * cell_w) if c < self.cols - 1 else width,
                    y2=int((r + 1) * cell_h) if r < self.rows - 1 else height,
                )

        # 2. Foot-point → 셀 매핑 (추적 ID 도 함께 모은다)
        members: Dict[Tuple[int, int], List[Tuple[int, int]]] = {k: [] for k in grid}
        ids = detection.track_ids or [None] * len(detection.foot_points)
        for (fx, fy), tid in zip(detection.foot_points, ids):
            c = max(0, min(self.cols - 1, int(fx / cell_w)))
            r = max(0, min(self.rows - 1, int(fy / cell_h)))
            grid[(r, c)].count += 1
            members[(r, c)].append((fx, fy))
            if tid is not None:
                grid[(r, c)].track_ids.append(int(tid))

        # 3. 면적·밀집도 산출 및 등급 판정
        cells = list(grid.values())
        alarm_reasons: List[str] = []
        calibrated = self.calibrated

        # 카메라와 고도를 알면 셀별 거리를 구해 검출 가능 범위를 판단한다
        max_range = None
        if self.camera is not None and altitude_m and altitude_m > 0:
            if (self.camera.width, self.camera.height) != (width, height):
                self.camera.width, self.camera.height = width, height
            max_range = self.camera.max_detection_range_m()

        for cell in cells:
            area = self._cell_area(cell, frame_shape)
            cell.area_m2 = area
            if area is not None and area >= self.min_cell_area_m2:
                cell.density = cell.count / area

            if max_range is not None:
                cell.slant_range_m = self.camera.slant_range_at(cell.center[1], altitude_m)
                cell.in_detection_range = (cell.slant_range_m is not None
                                           and cell.slant_range_m <= max_range)

            # 보이지 않는 구역의 "0명"은 "안전"이 아니다. 판정을 보류한다.
            if not cell.in_detection_range and cell.count == 0:
                cell.status = "UNKNOWN"
                continue

            if calibrated and cell.density is not None:
                if cell.density >= self.density_danger:
                    cell.status = "DANGER"
                    alarm_reasons.append(
                        f"Grid ({cell.row},{cell.col}) {cell.density:.2f} p/m^2 "
                        f">= {self.density_danger:.2f}"
                    )
                elif cell.density >= self.density_warn:
                    cell.status = "WARNING"
                elif cell.count > 0:
                    cell.status = "NORMAL"
                else:
                    cell.status = "EMPTY"
            elif calibrated and cell.count > 0:
                # 캘리브레이션은 됐으나 이 셀은 지평선 너머 — 판정 보류
                cell.status = "UNKNOWN"
            else:
                if cell.count >= self.danger_threshold:
                    cell.status = "DANGER"
                    alarm_reasons.append(
                        f"Grid ({cell.row},{cell.col}) count {cell.count} "
                        f">= {self.danger_threshold}"
                    )
                elif cell.count >= self.warn_threshold:
                    cell.status = "WARNING"
                elif cell.count > 0:
                    cell.status = "NORMAL"
                else:
                    cell.status = "EMPTY"

        # 4. 가장 혼잡한 셀 — 캘리브레이션 시 밀집도, 아니면 인원수 기준
        def rank(c: GridCell) -> float:
            if calibrated and c.density is not None:
                return c.density
            return float(c.count)

        populated = [c for c in cells if c.count > 0]
        max_cell = max(populated, key=rank) if populated else None

        # 5. 전체 과밀집 판정
        is_over = any(c.status == "DANGER" for c in cells)
        if detection.count >= self.total_threshold:
            is_over = True
            alarm_reasons.append(
                f"Total count {detection.count} >= {self.total_threshold}"
            )

        # 6. 타겟 좌표 — 셀 중심보다 실제 발목 무게중심이 정확하다
        target = None
        if max_cell is not None:
            pts = members[(max_cell.row, max_cell.col)]
            if pts:
                target = (int(sum(p[0] for p in pts) / len(pts)),
                          int(sum(p[1] for p in pts) / len(pts)))
            else:
                target = max_cell.center

        return DensityAnalysisResult(
            total_persons=detection.count,
            grid_cells=cells,
            max_dense_cell=max_cell,
            is_overcrowded=is_over,
            alarm_reasons=alarm_reasons,
            calibrated=calibrated,
            peak_density=(max_cell.density if max_cell else None),
            target_point=target,
        )

    # ───────────────────────── 시각화 ─────────────────────────
    def draw_visualization(
        self,
        frame: np.ndarray,
        detection: DetectionResult,
        analysis: DensityAnalysisResult,
        fps: float = 0.0,
        show_boxes: bool = True,
        show_footpoints: bool = True,
        show_grid: bool = True,
        show_heatmap: bool = True,
        alert_active: Optional[bool] = None,
        smoothed_count: Optional[int] = None,
        target_override: Optional[Tuple[int, int]] = None,
    ) -> np.ndarray:
        vis = frame.copy()
        overlay = frame.copy()

        color_map = {
            "EMPTY": (30, 30, 30),
            "NORMAL": (0, 200, 0),
            "WARNING": (0, 165, 255),
            "DANGER": (0, 0, 255),
            "UNKNOWN": (120, 120, 120),
        }

        if show_heatmap or show_grid:
            for cell in analysis.grid_cells:
                if show_heatmap and cell.count > 0:
                    cv2.rectangle(overlay, (cell.x1, cell.y1), (cell.x2, cell.y2),
                                  color_map.get(cell.status, (0, 200, 0)), -1)
                if show_grid:
                    danger = cell.status == "DANGER"
                    cv2.rectangle(vis, (cell.x1, cell.y1), (cell.x2, cell.y2),
                                  (0, 0, 255) if danger else (180, 180, 180),
                                  2 if danger else 1)
                    if cell.status == "UNKNOWN" and not cell.in_detection_range:
                        label = (f"[{cell.row},{cell.col}] too far "
                                 f"({cell.slant_range_m:.0f}m)"
                                 if cell.slant_range_m else
                                 f"[{cell.row},{cell.col}] too far")
                    elif cell.density is not None:
                        label = f"[{cell.row},{cell.col}] {cell.count}p  {cell.density:.1f}/m2"
                    elif cell.status == "UNKNOWN":
                        label = f"[{cell.row},{cell.col}] {cell.count}p  (no ground)"
                    else:
                        label = f"[{cell.row},{cell.col}] {cell.count}p"
                    for col, th in (((255, 255, 255), 2), ((0, 0, 0), 1)):
                        cv2.putText(vis, label, (cell.x1 + 8, cell.y1 + 22),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, th, cv2.LINE_AA)
            if show_heatmap:
                cv2.addWeighted(overlay, self.heatmap_alpha, vis,
                                1 - self.heatmap_alpha, 0, vis)

        if show_boxes:
            ids = detection.track_ids or [None] * len(detection.boxes)
            for (x1, y1, x2, y2), conf, tid in zip(detection.boxes,
                                                   detection.confidences, ids):
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
                tag = f"#{tid} {conf:.2f}" if tid is not None else f"P {conf:.2f}"
                cv2.putText(vis, tag, (x1, max(20, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA)

        if show_footpoints:
            for fx, fy in detection.foot_points:
                cv2.circle(vis, (fx, fy), 5, (0, 0, 255), -1)
                cv2.circle(vis, (fx, fy), 7, (255, 255, 255), 1)

        # ── HUD ──
        h, w = vis.shape[:2]
        hud_h = 92
        hud = np.zeros((hud_h, w, 3), dtype=np.uint8)
        vis[0:hud_h, 0:w] = cv2.addWeighted(vis[0:hud_h, 0:w], 0.4, hud, 0.6, 0)

        cal = "CALIBRATED" if analysis.calibrated else "UNCALIBRATED (raw counts)"
        trk = "TRACKING" if detection.tracked else "DETECT-ONLY"
        cv2.putText(vis, f"SHEPHERDRON VISION CORE | FPS {fps:.1f} | {trk} | {cal}",
                    (20, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)

        active = analysis.is_overcrowded if alert_active is None else alert_active
        col = (0, 0, 255) if active else (0, 255, 0)
        state = "OVER-DENSITY ALERT" if active else "NORMAL DENSITY"
        n = analysis.total_persons if smoothed_count is None else smoothed_count
        peak = (f"  |  peak {analysis.peak_density:.1f} p/m2"
                if analysis.peak_density is not None else "")
        cv2.putText(vis, f"Total {n}{peak}  |  {state}", (20, 54),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.68, col, 2, cv2.LINE_AA)

        if alert_active is not None and alert_active != analysis.is_overcrowded:
            cv2.putText(vis, "(debounced - raw frame disagrees)", (20, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.46, (0, 200, 255), 1, cv2.LINE_AA)

        tgt = target_override or analysis.target_point
        if active and tgt is not None:
            cx, cy = int(tgt[0]), int(tgt[1])
            cv2.drawMarker(vis, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 44, 2)
            cv2.circle(vis, (cx, cy), 26, (0, 0, 255), 1)
            mc = analysis.max_dense_cell
            if mc is not None:
                cv2.putText(vis, f"TARGET ({mc.row},{mc.col})", (cx - 62, cy - 34),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 0, 255), 2, cv2.LINE_AA)
        return vis
