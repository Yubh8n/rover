from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        # '' = find the Nucleo's ST-Link automatically (not the Pixhawk on /dev/ttyAMA0)
        DeclareLaunchArgument('stm32_port', default_value=''),
        DeclareLaunchArgument('stm32_baud', default_value='115200'),
        Node(
            package='rover_stm32',
            executable='stm32_link',
            name='stm32_link',
            output='screen',
            parameters=[{
                'port': LaunchConfiguration('stm32_port'),
                'baud': LaunchConfiguration('stm32_baud'),
                'info_period': 2.0,
            }],
        ),
    ])
