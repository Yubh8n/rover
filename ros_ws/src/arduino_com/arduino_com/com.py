import serial
import time
import rclpy
import math
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Int8
from geometry_msgs.msg import Twist, Vector3

class arduino_com(Node):
    def __init__(self):
        super().__init__('arduino_com')
        self.declare_parameter('track_width', 0.15)
        self.declare_parameter('wheel_diameter', 43.5/1000)
        self.declare_parameter('max_rpm', 159.0)
        self.twist_sub = self.create_subscription(Twist, "com/motor_twist", self.motor_twist, 1)
        self.ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
        time.sleep(2)
        self.ser.reset_input_buffer()
        self.timer = self.create_timer(0.1, self.test)
        self.L = 0
        self.R = 0
        self.response_gotten = True
        print("Arduino com ready. ")

    # FIT0441 (12VDC BLDC) #
    def motor_twist(self, data: Twist):
        track = self.get_parameter('track_width').value
        diam = self.get_parameter('wheel_diameter').value
        max_rpm = self.get_parameter('max_rpm').value

        v_l = data.linear.x - data.angular.z * track / 2.0
        v_r = data.linear.x + data.angular.z * track / 2.0

        rpm_l = v_l / (math.pi * diam) * 60.0
        rpm_r = v_r / (math.pi * diam) * 60.0

        # Clamp til motorens formåen — sendes som RPM direkte (Arduino PI-regulerer)
        self.L = int(max(-max_rpm, min(max_rpm, rpm_l)))
        self.R = int(max(-max_rpm, min(max_rpm, rpm_r)))

    def test(self):
        while self.ser.in_waiting > 0:
            line = self.ser.readline().decode('utf-8', errors='ignore').rstrip()
            if line:
                self.get_logger().info(line)
        self.ser.write(f"V {self.L} {self.R}\n".encode())

def main(args=None):
    rclpy.init(args=args)
    node = arduino_com()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()
