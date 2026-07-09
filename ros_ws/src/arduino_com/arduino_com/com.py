import serial
import threading
import time
import std_msgs
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int8

class arduino_com(Node):
    def __init__(self):
        super().__init__('arduino_com')
        self.sub = self.create_subscription(Int8, 'motor_speed', self.motor_callback, 1)
        self.ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
        time.sleep(2)
        self.ser.reset_input_buffer()

    #FIT0441 (12VDC BLDC)#
    def motor_callback(self, data):
        print(f'Sending: {data.data} to arduino')
        self.ser.write(f"V {data.data} -100\n".encode())


def main() -> None:
    rclpy.init()
    node = arduino_com()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    rclpy.shutdown()

    # ser.write(f"V 0 -100\n".encode())
    # while True:
    #     if ser.in_waiting > 0:
    #         line = ser.readline().decode('utf-8').rstrip()
    #         print(line)

if __name__ == '__main__':
    main()
