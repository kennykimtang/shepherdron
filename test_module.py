import numpy as np
import cv2
import os
from vision.detector import PersonDetector, DetectionResult
from vision.density_analyzer import DensityAnalyzer

def run_tests():
    print("[TEST] 1. Initializing PersonDetector...")
    detector = PersonDetector(model_name="yolov8n.pt", conf_threshold=0.45)
    
    # 640x480 더미 프레임 생성
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # 배경 약간 밝게
    dummy_frame[:] = (50, 50, 50)
    
    print("[TEST] 2. Running inference on dummy frame...")
    result = detector.detect(dummy_frame)
    print(f"       Inference success! Detected: {result.count} persons (Expected 0 on blank)")

    print("[TEST] 3. Testing DensityAnalyzer with simulated crowd...")
    analyzer = DensityAnalyzer(
        grid_rows=3,
        grid_cols=3,
        warn_threshold=2,
        danger_threshold=4,
        total_threshold=6
    )

    # 가상 바운딩 박스 & Foot-point (특정 셀에 집중된 군중 시뮬레이션)
    # (row 1, col 1) 셀 범위: x in [213, 426], y in [160, 320]
    simulated_boxes = [
        (250, 180, 280, 260),
        (290, 190, 320, 270),
        (330, 185, 360, 265),
        (300, 210, 330, 290),
        (350, 200, 380, 280), # 총 5명 -> Danger threshold(4) 초과
    ]
    simulated_footpoints = [
        (265, 260),
        (305, 270),
        (345, 265),
        (315, 290),
        (365, 280)
    ]
    
    sim_detection = DetectionResult(
        boxes=simulated_boxes,
        confidences=[0.85, 0.90, 0.78, 0.88, 0.92],
        foot_points=simulated_footpoints,
        count=len(simulated_boxes)
    )

    analysis = analyzer.analyze(dummy_frame.shape, sim_detection)
    print(f"       Total count: {analysis.total_persons}")
    print(f"       Is Overcrowded: {analysis.is_overcrowded}")
    print(f"       Max Dense Cell: ({analysis.max_dense_cell.row}, {analysis.max_dense_cell.col}) with {analysis.max_dense_cell.count} persons")
    print(f"       Alarm reasons: {analysis.alarm_reasons}")
    assert analysis.is_overcrowded == True, "Should be overcrowded!"

    print("[TEST] 4. Testing visualization rendering...")
    vis = analyzer.draw_visualization(
        frame=dummy_frame,
        detection=sim_detection,
        analysis=analysis,
        fps=30.0,
        show_boxes=True,
        show_footpoints=True,
        show_grid=True,
        show_heatmap=True
    )
    os.makedirs("test_output", exist_ok=True)
    out_path = "test_output/test_crowd_visualization.jpg"
    cv2.imwrite(out_path, vis)
    print(f"       Rendered visualization saved to {out_path}")
    print("[TEST] All unit & integration tests PASSED! 🎉")

if __name__ == "__main__":
    run_tests()
