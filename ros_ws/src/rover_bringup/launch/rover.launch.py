from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        # STM32 serial port: '' = find the Nucleo's ST-Link automatically
        DeclareLaunchArgument('stm32_port', default_value=''),

        # Kamera-node (C++)
        Node(
            package='cpp_pubsub',
            executable='publisher',
            name='webcam_stream',
            output='screen',
        ),

        # STM32-link: firmware-version, boot-status, opdatering og app-beskeder
        Node(
            package='rover_stm32',
            executable='stm32_link',
            name='stm32_link',
            output='screen',
            parameters=[{'port': LaunchConfiguration('stm32_port')}],
        ),
    ])
