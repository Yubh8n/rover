from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        # Kamera-node (C++)
        Node(
            package='cpp_pubsub',
            executable='publisher',
            name='webcam_stream',
            output='screen',
        ),
    ])