import serial, threading, time
ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
time.sleep(2)
ser.reset_input_buffer()


def main() -> None:
    ser.write(f"V 100 -100\n".encode())
    while True:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8').rstrip()
            print(line)

if __name__ == '__main__':
    main()
