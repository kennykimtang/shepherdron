import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional
from vision.detector import DetectionResult


@dataclass
class GridCell:
    row: int
    col: int
    x1: int
    y1: int
    x2: int
    y2: int
    count: int = 0
    status: str = "EMPTY"  # "EMPTY", "NORMAL", "WARNING", "DANGER"

    @property
    def center(self) -> Tuple[int, int]:
        return (int((self.x1 + self.x2) / 2), int((self.y1 + self.y2) / 2))


@dataclass
class DensityAnalysisResult:
    total_persons: int
    grid_cells: List[GridCell] = field(default_factory=list)
    max_dense_cell: Optional[GridCell] = None
    is_overcrowded: bool = False
    alarm_reasons: List[str] = field(default_factory=list)


class DensityAnalyzer:
    """
    영상 프레임을 그리드로 분할하고, Foot-point 기반으로
    각 영역의 인구 밀집도를 계산 및 과밀집 상태를 판정하는 분석기
    """

    def __init__(
        self,
        grid_rows: int = 3,
        grid_cols: int = 3,
        warn_threshold: int = 3,
        danger_threshold: int = 5,
        total_threshold: int = 15,
        heatmap_alpha: float = 0.35,
    ):
        self.rows = grid_rows
        self.cols = grid_cols
        self.warn_threshold = warn_threshold
        self.danger_threshold = danger_threshold
        self.total_threshold = total_threshold
        self.heatmap_alpha = heatmap_alpha

    def analyze(self, frame_shape: Tuple[int, int, int], detection: DetectionResult) -> DensityAnalysisResult:
        """
        검출 결과(발목 좌표)를 기반으로 그리드별 밀집도 집계 및 과밀집 판정
        """
        height, width = frame_shape[:2]
        cell_w = width / self.cols
        cell_h = height / self.rows

        # 1. 그리드 셀 초기화
        grid: Dict[Tuple[int, int], GridCell] = {}
        for r in range(self.rows):
            for c in range(self.cols):
                gx1 = int(c * cell_w)
                gy1 = int(r * cell_h)
                gx2 = int((c + 1) * cell_w) if c < self.cols - 1 else width
                gy2 = int((r + 1) * cell_h) if r < self.rows - 1 else height
                grid[(r, c)] = GridCell(row=r, col=c, x1=gx1, y1=gy1, x2=gx2, y2=gy2, count=0)

        # 2. Foot-point 기반 셀 매핑
        for foot_x, foot_y in detection.foot_points:
            c = int(foot_x / cell_w)
            r = int(foot_y / cell_h)
            # 영상 경계 클리핑
            c = max(0, min(self.cols - 1, c))
            r = max(0, min(self.rows - 1, r))
            grid[(r, c)].count += 1

        # 3. 셀 상태 분류 및 최대 밀집 셀 탐색
        cells_list = list(grid.values())
        max_cell = None
        max_count = -1
        alarm_reasons = []

        for cell in cells_list:
            if cell.count >= self.danger_threshold:
                cell.status = "DANGER"
                alarm_reasons.append(f"Grid ({cell.row},{cell.col}) count: {cell.count} >= {self.danger_threshold}")
            elif cell.count >= self.warn_threshold:
                cell.status = "WARNING"
            elif cell.count > 0:
                cell.status = "NORMAL"
            else:
                cell.status = "EMPTY"

            if cell.count > max_count:
                max_count = cell.count
                max_cell = cell

        # 4. 전체 과밀집(Over-density) 여부 판정
        is_overcrowded = False
        if detection.count >= self.total_threshold:
            is_overcrowded = True
            alarm_reasons.append(f"Total count: {detection.count} >= {self.total_threshold}")
        elif any(cell.status == "DANGER" for cell in cells_list):
            is_overcrowded = True

        return DensityAnalysisResult(
            total_persons=detection.count,
            grid_cells=cells_list,
            max_dense_cell=max_cell,
            is_overcrowded=is_overcrowded,
            alarm_reasons=alarm_reasons,
        )

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
    ) -> np.ndarray:
        """
        분석 결과를 프레임 위에 오버레이 렌더링
        """
        vis_frame = frame.copy()
        overlay = frame.copy()

        # 색상 맵 (BGR)
        color_map = {
            "EMPTY": (30, 30, 30),
            "NORMAL": (0, 200, 0),      # 초록
            "WARNING": (0, 165, 255),   # 주황
            "DANGER": (0, 0, 255),      # 빨강
        }

        # 1. 그리드 히트맵 및 경계선 그리기
        if show_heatmap or show_grid:
            for cell in analysis.grid_cells:
                if show_heatmap and cell.count > 0:
                    fill_color = color_map.get(cell.status, (0, 200, 0))
                    cv2.rectangle(overlay, (cell.x1, cell.y1), (cell.x2, cell.y2), fill_color, -1)

                if show_grid:
                    border_color = (0, 0, 255) if cell.status == "DANGER" else (180, 180, 180)
                    thickness = 2 if cell.status == "DANGER" else 1
                    cv2.rectangle(vis_frame, (cell.x1, cell.y1), (cell.x2, cell.y2), border_color, thickness)

                    # 셀 우측 상단 인원수 태그
                    label = f"[{cell.row},{cell.col}]: {cell.count}"
                    cv2.putText(
                        vis_frame,
                        label,
                        (cell.x1 + 8, cell.y1 + 22),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (255, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )
                    cv2.putText(
                        vis_frame,
                        label,
                        (cell.x1 + 8, cell.y1 + 22),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 0, 0),
                        1,
                        cv2.LINE_AA,
                    )

            if show_heatmap:
                cv2.addWeighted(overlay, self.heatmap_alpha, vis_frame, 1 - self.heatmap_alpha, 0, vis_frame)

        # 2. 바운딩 박스 그리기
        if show_boxes:
            for (x1, y1, x2, y2), conf in zip(detection.boxes, detection.confidences):
                cv2.rectangle(vis_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    vis_frame,
                    f"P {conf:.2f}",
                    (x1, max(20, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 255, 0),
                    1,
                    cv2.LINE_AA,
                )

        # 3. Foot-point (발목 좌표) 그리기
        if show_footpoints:
            for foot_x, foot_y in detection.foot_points:
                cv2.circle(vis_frame, (foot_x, foot_y), 5, (0, 0, 255), -1)
                cv2.circle(vis_frame, (foot_x, foot_y), 7, (255, 255, 255), 1)

        # 4. 상단 대시보드 HUD 오버레이
        h, w = vis_frame.shape[:2]
        hud_h = 70
        hud_bg = np.zeros((hud_h, w, 3), dtype=np.uint8)
        hud_alpha = 0.6
        vis_frame[0:hud_h, 0:w] = cv2.addWeighted(vis_frame[0:hud_h, 0:w], 1 - hud_alpha, hud_bg, hud_alpha, 0)

        # 텍스트 정보 출력
        title_text = f"SHEPHERDRON VISION CORE | FPS: {fps:.1f}"
        cv2.putText(vis_frame, title_text, (20, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 2, cv2.LINE_AA)

        density_color = (0, 0, 255) if analysis.is_overcrowded else (0, 255, 0)
        status_text = "OVER-DENSITY ALERT!" if analysis.is_overcrowded else "NORMAL DENSITY"
        info_text = f"Total: {analysis.total_persons}  |  Status: {status_text}"
        cv2.putText(vis_frame, info_text, (20, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.7, density_color, 2, cv2.LINE_AA)

        # 과밀집 발생 시 타겟 셀 강조 표시
        if analysis.is_overcrowded and analysis.max_dense_cell:
            mc = analysis.max_dense_cell
            # 타겟 셀에 조준선(Target Crosshair) 그리기
            cx, cy = mc.center
            cv2.drawMarker(vis_frame, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 40, 2)
            cv2.putText(
                vis_frame,
                f"TARGET CELL ({mc.row},{mc.col})",
                (cx - 60, cy - 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

        return vis_frame
