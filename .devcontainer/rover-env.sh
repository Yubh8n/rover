# rover-env.sh - shell helpers for the dev container, sourced from ~/.bashrc
# (added by postCreateCommand in devcontainer.json).
#
#   rover-on      use the Fast DDS discovery server on the Pi (rover101.local),
#                 so ros2 sees the Rover's nodes (mavros, stm32_link, ...)
#   rover-off     back to local discovery (container only, e.g. the STM32 simulator)
#   rover-status  which mode, and is the Pi reachable
#
# The choice is remembered in ~/.rover_net, so new terminals follow it.

ROVER_HOST="${ROVER_HOST:-rover101.local}"
ROVER_DDS_PORT="${ROVER_DDS_PORT:-11811}"
ROVER_NET_FILE="$HOME/.rover_net"

_rover_apply() {   # on|off, no output
  if [ "$1" = on ]; then
    export ROS_DISCOVERY_SERVER="$ROVER_HOST:$ROVER_DDS_PORT"
    export ROS_SUPER_CLIENT=TRUE      # ros2 CLI tools see every node, not only their own
  else
    unset ROS_DISCOVERY_SERVER ROS_SUPER_CLIENT
  fi
}

_rover_restart_daemon() {
  # The ros2 daemon keeps the discovery settings it was started with, so restart
  # it with the new ones. Start it explicitly: a daemon that a `ros2 topic list`
  # spawns by itself right after the stop can end up seeing only local topics.
  command -v ros2 >/dev/null || return 0
  ros2 daemon stop >/dev/null 2>&1
  ros2 daemon start >/dev/null 2>&1
}

rover-on() {
  if ! getent hosts "$ROVER_HOST" >/dev/null; then
    echo "warning: $ROVER_HOST does not resolve (Pi off, or no mDNS in this container?)"
  fi
  echo on > "$ROVER_NET_FILE"
  _rover_apply on
  _rover_restart_daemon
  echo "rover: discovery server $ROS_DISCOVERY_SERVER"
  echo "       give discovery ~5 s, then: ros2 topic list"
  echo "       other open terminals: run rover-on there too"
}

rover-off() {
  echo off > "$ROVER_NET_FILE"
  _rover_apply off
  _rover_restart_daemon
  echo "rover: local discovery only"
  echo "       other open terminals: run rover-off there too"
}

rover-status() {
  if [ -n "${ROS_DISCOVERY_SERVER:-}" ]; then
    echo "mode : on  (ROS_DISCOVERY_SERVER=$ROS_DISCOVERY_SERVER)"
  else
    echo "mode : off (local discovery)"
  fi
  local ip
  ip="$(getent hosts "$ROVER_HOST" | awk '{print $1; exit}')"
  if [ -z "$ip" ]; then
    echo "pi   : $ROVER_HOST does not resolve"
  elif ping -c1 -W1 "$ip" >/dev/null 2>&1; then
    echo "pi   : $ROVER_HOST = $ip, reachable"
  else
    echo "pi   : $ROVER_HOST = $ip, not answering ping"
  fi
}

# New shell: follow the last choice (default off)
_rover_apply "$(cat "$ROVER_NET_FILE" 2>/dev/null || echo off)"
