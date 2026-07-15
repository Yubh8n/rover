import serial
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import UInt8

class arduino_com(Node):
    def __init__(self):
        super().__init__('arduino_com')
        self.sub = self.create_subscription(UInt8, 'motor_speed', self.motor_callback, 1)
        self.ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
        time.sleep(2)
        self.ser.reset_input_buffer()
        self.timer = self.create_timer(0.1, self.test)
        self.L = 0
        self.R = 0
        self.response_gotten = True
        print("Arduino com ready. ")

    # FIT0441 (12VDC BLDC) #
    def motor_callback(self, data):
        self.response_gotten = False
        self.L = data.data
        self.R = data.data
        print(f'Sending: {data.data} to arduino')

    def test(self):
        if self.ser.in_waiting > 0:
            line = self.ser.readline().decode('utf-8').rstrip()
            self.get_logger().info(line)
            self.response_gotten = True
        if not self.response_gotten:
            self.ser.write(f"V {self.L} {self.R}\n".encode())

def main() -> None:
    rclpy.init()
    node = arduino_com()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    rclpy.shutdown()

    # while True:
    #     if ser.in_waiting > 0:
    #         line = ser.readline().decode('utf-8').rstrip()
    #         print(line)

if __name__ == '__main__':
    main()
