#!/usr/bin/env python3
"""Live ChArUco camera calibration tool.

Move the board (or phone showing it) around in front of the camera. Press
'c' to capture a view once enough corners are detected, 'q' to finish and
run the calibration, ESC to abort without calibrating.

Board parameters default to the same values as charuco_detector's
config/charuco.yaml, so you can reuse that file directly:

    ros2 run charuco_detector calibrate_charuco.py --ros-args \
        --params-file src/charuco_detector/config/charuco.yaml \
        -p output_path:=camera_info.yaml
"""
import cv2
import numpy as np
import rclpy
import yaml
from cv2 import aruco
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage

WINDOW = "charuco calibration  [c]=capture  [q]=calibrate & save  [ESC]=abort"


class CalibrationNode(Node):

    def __init__(self):
        super().__init__("charuco_calibrator")

        squares_x = self.declare_parameter("squares_x", 5).value
        squares_y = self.declare_parameter("squares_y", 7).value
        square_length = self.declare_parameter("square_length", 0.04).value
        marker_length = self.declare_parameter("marker_length", 0.03).value
        dict_id = self.declare_parameter("dictionary_id", int(aruco.DICT_5X5_1000)).value
        self.min_corners = self.declare_parameter("min_corners", 6).value
        image_topic = self.declare_parameter("image_topic", "/camera/image").value
        self.output_path = self.declare_parameter("output_path", "camera_info.yaml").value
        self.camera_name = self.declare_parameter("camera_name", "camera").value

        dictionary = aruco.getPredefinedDictionary(dict_id)
        self.board = aruco.CharucoBoard((squares_x, squares_y), square_length, marker_length, dictionary)
        params = aruco.DetectorParameters()
        params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
        self.detector = aruco.CharucoDetector(self.board, aruco.CharucoParameters(), params)

        self.obj_points_views = []
        self.img_points_views = []
        self.image_size = None
        self.latest_frame = None
        self.latest_overlay = None
        self.latest_count = 0
        self.latest_corners = None
        self.latest_ids = None

        topic = image_topic.rstrip("/") + "/compressed"
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )
        self.sub = self.create_subscription(CompressedImage, topic, self.on_image, qos)
        self.get_logger().info(f"Subscribed to {topic}, waiting for frames...")

    def on_image(self, msg: CompressedImage):
        arr = np.frombuffer(msg.data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return
        self.image_size = (img.shape[1], img.shape[0])

        charuco_corners, charuco_ids, marker_corners, marker_ids = self.detector.detectBoard(img)
        overlay = img.copy()
        if marker_ids is not None and len(marker_ids) > 0:
            aruco.drawDetectedMarkers(overlay, marker_corners, marker_ids)
        count = 0 if charuco_ids is None else len(charuco_ids)
        if charuco_ids is not None and count > 0:
            aruco.drawDetectedCornersCharuco(overlay, charuco_corners, charuco_ids, (0, 255, 0))

        for corners in self.img_points_views:
            for pt in corners.reshape(-1, 2):
                cv2.circle(overlay, (int(pt[0]), int(pt[1])), 3, (0, 0, 255), -1)

        cv2.putText(overlay, f"captured: {len(self.obj_points_views)}   corners now: {count}",
                    (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        self.latest_frame = img
        self.latest_overlay = overlay
        self.latest_count = count
        self.latest_corners = charuco_corners
        self.latest_ids = charuco_ids

    def try_capture(self):
        if self.latest_count < self.min_corners:
            self.get_logger().warn(
                f"Only {self.latest_count} corners visible (need >= {self.min_corners}), not captured.")
            return
        obj_pts, img_pts = self.board.matchImagePoints(self.latest_corners, self.latest_ids)
        if obj_pts is None or len(obj_pts) < 4:
            self.get_logger().warn("Could not match enough object/image points, not captured.")
            return
        self.obj_points_views.append(obj_pts)
        self.img_points_views.append(img_pts)
        self.get_logger().info(f"Captured view {len(self.obj_points_views)} ({self.latest_count} corners).")

    def calibrate_and_save(self):
        if len(self.obj_points_views) < 4:
            self.get_logger().error(
                f"Only {len(self.obj_points_views)} views captured, need at least 4 (15-20+ recommended). Aborting.")
            return False

        ret, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(
            self.obj_points_views, self.img_points_views, self.image_size, None, None)

        self.get_logger().info(f"Calibration done. Reprojection error: {ret:.4f} px")
        self.get_logger().info(f"camera_matrix:\n{camera_matrix}")
        self.get_logger().info(f"dist_coeffs: {dist_coeffs.ravel()}")

        w, h = self.image_size
        fx, fy = camera_matrix[0, 0], camera_matrix[1, 1]
        cx, cy = camera_matrix[0, 2], camera_matrix[1, 2]
        d = dist_coeffs.ravel().tolist()

        data = {
            "image_width": w,
            "image_height": h,
            "camera_name": self.camera_name,
            "camera_matrix": {"rows": 3, "cols": 3, "data": camera_matrix.flatten().tolist()},
            "distortion_model": "plumb_bob",
            "distortion_coefficients": {"rows": 1, "cols": len(d), "data": d},
            "rectification_matrix": {"rows": 3, "cols": 3, "data": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]},
            "projection_matrix": {
                "rows": 3, "cols": 4,
                "data": [fx, 0.0, cx, 0.0, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0],
            },
        }
        with open(self.output_path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=None)
        self.get_logger().info(f"Saved calibration to {self.output_path}")
        return True


def main():
    rclpy.init()
    node = CalibrationNode()
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.01)
            if node.latest_overlay is not None:
                cv2.imshow(WINDOW, node.latest_overlay)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC
                node.get_logger().info("Aborted, nothing saved.")
                break
            elif key == ord('c'):
                node.try_capture()
            elif key == ord('q'):
                node.calibrate_and_save()
                break
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
