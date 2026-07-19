#!/usr/bin/env bash
set -e

WS=/home/cbm/rover/ros_ws
HOME=/home/cbm

# ROS2 Jazzy base environment
source /opt/ros/jazzy/setup.bash

# 1. Byg workspace
cd "$WS"
colcon build

# 2.5 Go home
cd "$HOME"

# 2. Source install
source "$WS/install/local_setup.sh"

# 3. Kør launch-fil
ros2 launch rover_bringup rover.launch.py