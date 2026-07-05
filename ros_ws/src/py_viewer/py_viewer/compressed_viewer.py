#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage
import numpy as np
import cv2

class CompressedViewer(Node):
    def __init__(self):
        super().__init__('compressed_viewer')
        self.sub = self.create_subscription(
            CompressedImage,
            '/camera/image/compressed',
            self.callback,
            qos_profile_sensor_data)   # <-- matcher din publishers SensorDataQoS

    def callback(self, msg):
        arr = np.frombuffer(msg.data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            self.get_logger().warn('Kunne ikke dekode frame')
            return
        cv2.imshow('Camera', frame)
        cv2.waitKey(1)

def main():
    rclpy.init()
    node = CompressedViewer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    cv2.destroyAllWindows()
    rclpy.shutdown()

if __name__ == '__main__':
    main()