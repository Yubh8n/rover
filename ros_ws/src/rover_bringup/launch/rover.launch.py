from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        # Seriel bro til Arduino (motorstyring)
        Node(
            package='arduino_com',
            executable='com',
            name='arduino_com',
            parameters=[{
                'port': '/dev/ttyAMA0',
                'baudrate': 115200,
            }],
            output='screen',
        ),

        # Kamera-node (C++)
        Node(
            package='cpp_pubsub',
            executable='publisher',
            name='webcam_stream',
            output='screen',
        ),
    ])