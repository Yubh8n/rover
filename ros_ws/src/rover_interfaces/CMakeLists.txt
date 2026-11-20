cmake_minimum_required(VERSION 3.10)
project(rover_interfaces)

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/FirmwareSlot.msg"
  "msg/FirmwareInfo.msg"
  "msg/Stm32Frame.msg"
  "srv/GetFirmwareInfo.srv"
  "srv/ActivateSlot.srv"
  "srv/UpdateFirmware.srv"
  "srv/Stm32Request.srv"
  DEPENDENCIES builtin_interfaces
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
