# Rover ROS 2 working container: ROS 2 Jazzy + workspace deps + Claude Code.
#
# VS Code opens the repo inside this container (Dev Containers). See
# devcontainer.json for the mounts: the repo, ~/.claude (Claude's memory and
# login), ~/.ssh, /dev (cameras, serial), X11 and host networking (DDS).
FROM ros:jazzy

ARG USERNAME=cbm
ARG USER_UID=1000
ARG USER_GID=1000
ENV DEBIAN_FRONTEND=noninteractive

# Dependencies of the packages in ros_ws/src (from their package.xml files)
# plus the working environment: git, ssh to the Pi / GitHub, curl for the Claude installer
RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-jazzy-cv-bridge ros-jazzy-image-transport ros-jazzy-compressed-image-transport \
        ros-jazzy-message-filters ros-jazzy-tf2 ros-jazzy-tf2-ros ros-jazzy-tf2-geometry-msgs \
        ros-jazzy-geometry-msgs ros-jazzy-sensor-msgs ros-jazzy-std-msgs \
        ros-jazzy-teleop-twist-keyboard ros-jazzy-rqt-image-view \
        libopencv-dev python3-opencv python3-numpy python3-yaml python3-pytest \
        python3-colcon-common-extensions python3-rosdep python3-serial \
        v4l-utils usbutils \
        git openssh-client ca-certificates curl sudo less nano bash-completion \
        iputils-ping iproute2 \
        libnss-mdns \
    && rm -rf /var/lib/apt/lists/*

# mDNS: resolve <name>.local (e.g. rover101.local, the Pi) through the host's
# avahi-daemon, whose socket devcontainer.json mounts in. libnss-mdns adds
# "mdns4_minimal" to /etc/nsswitch.conf; make sure it is there.
RUN grep -q mdns4_minimal /etc/nsswitch.conf \
    || sed -i 's/^hosts:.*/hosts:          files mdns4_minimal [NOTFOUND=return] dns/' /etc/nsswitch.conf

# Same user name and uid as on the host, so files keep the right owner and the
# paths (/home/<you>/...) are identical. The Ubuntu 24.04 base ships a user
# "ubuntu" with uid 1000 - replace it.
RUN if id ubuntu >/dev/null 2>&1; then userdel -r ubuntu; fi \
    && groupadd -g "$USER_GID" "$USERNAME" \
    && useradd -m -s /bin/bash -u "$USER_UID" -g "$USER_GID" -G dialout,plugdev,video "$USERNAME" \
    && echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/$USERNAME" \
    && chmod 0440 "/etc/sudoers.d/$USERNAME"

USER $USERNAME
WORKDIR /home/$USERNAME

# Every shell gets ROS, plus the workspace overlay once it has been built
RUN echo 'source /opt/ros/jazzy/setup.bash' >> ~/.bashrc \
    && echo 'WS_SETUP="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null)/ros_ws/install/local_setup.bash"; [ -f "$WS_SETUP" ] && source "$WS_SETUP"' >> ~/.bashrc

# Claude Code (native installer -> ~/.local/bin/claude)
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH=/home/$USERNAME/.local/bin:$PATH
