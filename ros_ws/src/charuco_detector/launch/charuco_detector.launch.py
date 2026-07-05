import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory("charuco_detector")
    default_params = os.path.join(pkg_share, "config", "charuco.yaml")

    params_arg = DeclareLaunchArgument(
        "params_file",
        default_value=default_params,
        description="Path to the ChArUco detector parameter file.",
    )
    image_arg = DeclareLaunchArgument(
        "image_topic",
        default_value="/image_raw",
        description="Raw camera image topic to subscribe to.",
    )
    info_arg = DeclareLaunchArgument(
        "camera_info_topic",
        default_value="/camera_info",
        description="CameraInfo topic (intrinsics) to subscribe to.",
    )

    node = Node(
        package="charuco_detector",
        executable="charuco_detector_node",
        name="charuco_detector",
        output="screen",
        parameters=[LaunchConfiguration("params_file")],
        remappings=[
            ("image_raw", LaunchConfiguration("image_topic")),
            ("camera_info", LaunchConfiguration("camera_info_topic")),
        ],
    )

    return LaunchDescription([params_arg, image_arg, info_arg, node])
