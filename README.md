# rover-ros2

The ROS 2 (Jazzy) software for the Rover: the code that runs on the Rover's
**Raspberry Pi 5**, the tools to build and test it on your PC, and the tool that
ships it to the Pi.

This README explains **what is here, why it is built this way, and how to use
it**, including the ROS 2 basics you need to follow along. Read it top to bottom
once; afterwards the [cheat sheet](#1-cheat-sheet) and
[troubleshooting](#12-troubleshooting) sections are the ones you will come back to.

Your original Danish notes are kept unchanged at the end: [Notes](#notes-original).

---

## Contents

1. [Cheat sheet](#1-cheat-sheet)
2. [The big picture](#2-the-big-picture)
3. [What is in this repo](#3-what-is-in-this-repo)
4. [ROS 2 in five minutes](#4-ros-2-in-five-minutes)
5. [The dev container (your PC)](#5-the-dev-container-your-pc)
6. [Seeing the Rover from your PC: rover-on / rover-off](#6-seeing-the-rover-from-your-pc-rover-on--rover-off)
7. [The packages](#7-the-packages)
8. [The STM32 link in depth](#8-the-stm32-link-in-depth)
9. [Deploying to the Rover: tools/deploy-rover.sh](#9-deploying-to-the-rover-toolsdeploy-roversh)
10. [What runs on the Raspberry Pi](#10-what-runs-on-the-raspberry-pi)
11. [Testing](#11-testing)
12. [Troubleshooting](#12-troubleshooting)
13. [Known gaps and loose ends](#13-known-gaps-and-loose-ends)
14. [Glossary](#14-glossary)
15. [Notes (original)](#notes-original)

---

## 1. Cheat sheet

**On your PC** (in a VS Code terminal inside the dev container):

```sh
# Build and use the workspace
cd ros_ws
colcon build                      # compile every package in ros_ws/src
source install/setup.bash         # make the built packages visible in THIS terminal

# See what runs on the Rover
rover-on                          # talk to the Rover's ROS network (Pi = rover101.local)
ros2 topic list                   # wait ~5 s after rover-on the first time
ros2 topic echo /stm32_link/firmware_info     # STM32 firmware version + boot state
rover-off                         # back to "only this PC"
rover-status                      # which mode am I in, is the Pi reachable?

# Ship the current code to the Rover
tools/deploy-rover.sh             # build + test here, build + test on Pi, activate, reboot
tools/deploy-rover.sh --build-only    # same, but don't change what the Rover runs
tools/deploy-rover.sh --rollback      # go back to the version before
tools/deploy-rover.sh --status        # what is installed on the Pi

# Log in to the Pi
ssh cbm@rover101.local
```

**On the Pi** (`ssh cbm@rover101.local`):

```sh
systemctl status rover            # is the Rover stack running?
journalctl -u rover -f            # its live log (Ctrl-C to stop watching)
sudo systemctl restart rover      # restart the stack
sudo systemctl stop rover         # stop it (e.g. before using fwupdate.py on the STM32)
```

---

## 2. The big picture

```
 Your PC (cbm-B460HD3)                          The Rover
 ┌──────────────────────────────┐              ┌───────────────────────────────────────────────┐
 │ VS Code                      │              │ Raspberry Pi 5  "rover101" (rover101.local)   │
 │  └─ dev container            │   Wi-Fi /    │  Debian 13 + ROS 2 Jazzy                       │
 │      ROS 2 Jazzy, colcon,    │   network    │                                               │
 │      Claude Code, ssh        │◄────────────►│  DDS.service    discovery server :11811       │
 │                              │  ROS 2 (DDS) │  mavros.service  ──UART /dev/ttyAMA0──► Pixhawk 6C
 │  tools/deploy-rover.sh ──────┼── ssh ──────►│  rover.service  (rover.launch.py)             │
 │                              │              │     ├─ webcam_stream (camera, USB)            │
 └──────────────────────────────┘              │     └─ stm32_link ──USB /dev/ttyACM0──┐       │
                                               └──────────────────────────────────────┼───────┘
                                                                                      ▼
                                                      NUCLEO-G431KB (STM32) ──PWM──► motor drivers
                                                      firmware: separate repo rover-firmware
```

- The **Pixhawk 6C** runs ArduPilot (the autopilot). The Pi talks to it through
  **MAVROS**, which turns MAVLink into ROS 2 topics (`/mavros/...`).
- The **STM32** (a NUCLEO-G431KB board) reads the Pixhawk's throttle PWM signals
  and drives the two motor drivers. Its firmware lives in the separate
  [rover-firmware](https://github.com/Yubh8n/rover-firmware) repo. It has a
  bootloader with two firmware slots (A/B) and can be updated over its USB serial
  port.
- This repo adds **`stm32_link`**, a ROS 2 node on the Pi that talks to the STM32
  over that USB serial port: it reports the firmware version and boot state, and
  can update the firmware.
- Your **PC** is where you write and test code. `tools/deploy-rover.sh` sends it to
  the Pi, builds it there, and restarts the Rover with it.

---

## 3. What is in this repo

```
rover-ros2/
├── README.md               this file
├── notes.txt               your older notes (kept)
├── run.sh                  your old start script (kept; see "Known gaps")
├── .gitignore              what git must never commit (build output, caches, .vscode, ...)
├── .devcontainer/          the dev container: the Linux + ROS 2 environment VS Code opens
│   ├── Dockerfile              what is installed in it
│   ├── devcontainer.json       how it is started (mounts, network, USB, ...)
│   └── rover-env.sh            the rover-on / rover-off / rover-status commands
├── tools/
│   ├── deploy-rover.sh         build, test, ship to the Pi, activate, reboot
│   └── rover.service           systemd unit that starts the Rover stack at boot on the Pi
└── ros_ws/                 the ROS 2 workspace
    ├── src/                    source code: one folder per ROS 2 package
    │   ├── rover_bringup/          the launch file that starts the Rover stack
    │   ├── cpp_pubsub/             camera node (C++)
    │   ├── rover_stm32/            STM32 link node (Python)
    │   ├── rover_interfaces/       message and service definitions for the STM32 link
    │   ├── charuco_detector/       ChArUco board pose detection (C++)
    │   └── py_viewer/              shows the camera stream in a window (Python)
    ├── build/   install/   log/    created by colcon build - never committed
```

Only `src/` is source. `build/`, `install/` and `log/` are generated by
`colcon build` and can always be deleted and rebuilt.

---

## 4. ROS 2 in five minutes

Just enough to understand the rest of this README.

**Node** - one running program that does one job, e.g. `stm32_link` or the camera
node. Many nodes together make the robot.

**Topic** - a named channel that nodes publish messages on, and other nodes
subscribe to. Fire-and-forget, many-to-many. Example:
`/stm32_link/firmware_info`. Every topic has a **message type**, e.g.
`rover_interfaces/msg/FirmwareInfo` (a fixed set of fields).

```sh
ros2 topic list                      # all topics
ros2 topic echo <topic>              # print the messages
ros2 topic echo --once <topic>       # print one, then stop
ros2 topic hz <topic>                # how often messages arrive
ros2 topic info -v <topic>           # who publishes / subscribes, with QoS
```

**Service** - a request/response call to a node (like a function call), e.g.
"give me the firmware info now" or "update the firmware".

```sh
ros2 service list
ros2 service call /stm32_link/get_info rover_interfaces/srv/GetFirmwareInfo
```

**Parameter** - a setting of a node, given at start, e.g. the serial port:
`ros2 run rover_stm32 stm32_link --ros-args -p port:=/dev/ttyACM0`.

**Package** - a folder in `ros_ws/src` with a `package.xml` (name, dependencies)
and either a `CMakeLists.txt` (C++, *ament_cmake*) or a `setup.py` (Python,
*ament_python*). A package contains nodes, launch files, message definitions...

**Workspace** - the `ros_ws` folder. Build it with **colcon**:

```sh
cd ros_ws
colcon build                         # build all packages -> build/ and install/
colcon build --packages-select rover_stm32   # just one package (and only it)
source install/setup.bash            # REQUIRED in every new terminal before ros2 run/launch
```

`source install/setup.bash` adds your built packages on top of the base ROS
installation (`/opt/ros/jazzy`, which the container sources automatically). If
`ros2 run` says "package not found", you forgot this or the build failed.

**Launch file** - a Python file that starts several nodes with their parameters
at once: `ros2 launch rover_bringup rover.launch.py`.

**DDS and discovery** - ROS 2 nodes find each other with DDS. By default every
node shouts "I'm here" with multicast on the network. Multicast is unreliable
over Wi-Fi, so the Rover uses a **Fast DDS discovery server** instead: a small
program on the Pi (`DDS.service`, port 11811) that every node registers with.
A node only uses the server if `ROS_DISCOVERY_SERVER` is set. That is what
[`rover-on`](#6-seeing-the-rover-from-your-pc-rover-on--rover-off) does.

**ROS_DOMAIN_ID** - nodes only see nodes with the same domain id. Everything here
uses `0`.

**The ros2 daemon** - a background helper that caches what `ros2 topic list` etc.
see. It keeps the discovery settings it was started with, so after changing
`ROS_DISCOVERY_SERVER` it must be restarted (`rover-on`/`rover-off` do that).

---

## 5. The dev container (your PC)

### What and why

A **dev container** is a Docker container that VS Code opens your project in.
Everything you need (Ubuntu 24.04, ROS 2 Jazzy, colcon, OpenCV, pyserial, ssh,
Claude Code) is installed *in the container*, so your PC itself stays clean and
the setup is the same every time.

Open it: VS Code -> Command Palette (`Ctrl+Shift+P`) -> **Dev Containers: Reopen
in Container**. After changing `.devcontainer/Dockerfile` or `devcontainer.json`,
use **Dev Containers: Rebuild Container**.

Your terminal prompt still says `cbm@cbm-B460HD3` inside the container, because
the container shares the PC's network and hostname. To check where you are:
`[ -f /.dockerenv ] && echo container || echo host`.

### What `devcontainer.json` sets up, and why

| Setting | Why |
|---|---|
| Repo mounted at the **same path** as on the PC (`/home/cbm/Documents/github/rover-ros2`) | Claude Code finds its memory for a project by its path, so it is the same inside and outside. Build paths also stay valid. |
| `~/.claude` mounted | Claude Code's memory, settings and login are shared with the PC. |
| `~/.claude.json` copied in at creation | Claude's login file. Copied, not mounted, because Claude rewrites it in a way a file mount breaks. |
| `~/.ssh` mounted read-only + SSH agent forwarded | `ssh cbm@rover101.local` and `git push` work with your keys. |
| `--network=host`, `--ipc=host` | The container uses the PC's network directly, so ROS 2/DDS can talk to the Pi. |
| `--privileged`, `/dev` mounted | USB devices (cameras, serial ports, an STM32 board) work, also when plugged in later. |
| `/tmp/.X11-unix` + `DISPLAY` | GUI windows (rqt, rviz2, `py_viewer`) show on your screen. Run `xhost +local:` on the PC once per login if windows don't appear. |
| `/run/avahi-daemon` mounted + `libnss-mdns` installed | `.local` names (mDNS, e.g. `rover101.local`) resolve inside the container through the PC's Avahi daemon. |
| `ROS_DOMAIN_ID=0` | Same domain as the Rover. |
| `postCreateCommand` | Copies the Claude login and adds the `rover-*` commands to `~/.bashrc`. |

The `Dockerfile` installs ROS 2 Jazzy (base image `ros:jazzy`), the dependencies of
the packages in `ros_ws/src`, colcon, `python3-serial`, `libnss-mdns`, git/ssh and
Claude Code, and creates your user (`cbm`, same uid as on the PC so file
ownership is right). Every shell sources ROS, and - when the terminal opens
inside the repo - also `ros_ws/install`, once it has been built.

---

## 6. Seeing the Rover from your PC: rover-on / rover-off

The Rover's nodes (MAVROS, `stm32_link`, the camera) register with the discovery
server on the Pi. Your PC only sees them if it uses that server too.
`.devcontainer/rover-env.sh` gives you three commands for that:

| Command | What it does |
|---|---|
| `rover-on` | Sets `ROS_DISCOVERY_SERVER=rover101.local:11811` and `ROS_SUPER_CLIENT=TRUE`, restarts the ros2 daemon. Now `ros2 topic list` shows the Rover. |
| `rover-off` | Removes those settings, restarts the daemon. ROS only sees nodes on this PC. |
| `rover-status` | Shows the mode and whether `rover101.local` resolves and answers ping. |

- `ROS_SUPER_CLIENT=TRUE` makes command line tools see *every* node via the
  server (normal clients only learn about the topics they use themselves).
- The choice is saved in `~/.rover_net`, so **new** terminals start in the last
  mode. Terminals that are already open keep their mode until you run the
  command there too.
- Default is **off**, because with it on and the Pi switched off, nodes on your
  PC can't find each other either (e.g. when testing with the STM32 simulator).
- After `rover-on`, give discovery about 5 seconds before the first
  `ros2 topic list`.

Outside the container (on the PC itself) these commands don't exist; there you
can do the same by hand:

```sh
export ROS_DISCOVERY_SERVER=rover101.local:11811
export ROS_SUPER_CLIENT=TRUE
ros2 daemon stop; ros2 daemon start
```

---

## 7. The packages

### rover_bringup - starts the Rover

`launch/rover.launch.py` is what `rover.service` runs on the Pi at boot. It starts:

| Node | From package | Does |
|---|---|---|
| `webcam_stream` | `cpp_pubsub` (executable `publisher`) | camera -> `/camera/image/compressed` |
| `stm32_link` | `rover_stm32` | STM32 firmware info, update, messages |

Launch argument `stm32_port` (default empty = find the board automatically):
`ros2 launch rover_bringup rover.launch.py stm32_port:=/dev/ttyACM0`.

To add a node to the Rover: add a `Node(...)` to this file, add the package as
`<exec_depend>` in `rover_bringup/package.xml`, deploy.

### cpp_pubsub - the camera node (C++)

`src/simple_publisher.cpp`, executable `publisher`. Opens the first camera
(`/dev/video0`) with V4L2 at 640x480, 30 fps, in **MJPEG** mode and with
`CONVERT_RGB` off: it gets the camera's JPEG bytes and publishes them **without
decoding** as `sensor_msgs/CompressedImage` on **`/camera/image/compressed`**
(sensor-data QoS, i.e. best effort). That keeps the CPU load on the Pi low.
Exposure is set manually (`900`). It also creates `/topic` and `/camera/mjpg`
publishers that are currently unused.

If no camera is found, the node stops with "Kunne ikke åbne kamera"; the other
nodes keep running.

### py_viewer - look at the camera (Python)

`ros2 run py_viewer compressed_viewer` subscribes to `/camera/image/compressed`,
decodes the JPEGs and shows them in a window. Run it on your PC with `rover-on`
to see the Rover's camera (needs the X11 setup from section 5).

### charuco_detector - board pose from the camera (C++)

Detects a ChArUco calibration board in the camera image and publishes its pose:

- input: `image_topic` (default `/camera/image`, with `image_transport`
  `compressed` -> it reads `/camera/image/compressed`) **plus** a
  `sensor_msgs/CameraInfo` topic with the camera's calibration (intrinsics).
- output: `charuco/pose` (PoseStamped), `charuco/detected` (Bool),
  `charuco/debug_image`, and a TF `camera -> charuco_board`.
- settings: `config/charuco.yaml` (board 5x7 squares, 4 cm squares, 3 cm
  markers, dictionary DICT_5X5_1000).
- start: `ros2 launch charuco_detector charuco_detector.launch.py`
- `scripts/calibrate_charuco.py` - camera calibration with the board.

It is **not** started by `rover.launch.py`. Note: the camera node does not publish
a `CameraInfo` yet, so this node gets no pose until something does (see
[Known gaps](#13-known-gaps-and-loose-ends)).

It needs OpenCV **4.7 or newer** (`cv::aruco::ArucoDetector`/`CharucoDetector`).
The Pi has 4.10, the dev container (Ubuntu 24.04) only 4.6 - so it can't be built
in the container; the deploy script skips it there and builds it on the Pi.

One compatibility fix was made: Jazzy's `message_filters` wants an
`rmw_qos_profile_t`, newer ROS versions (Kilted/Lyrical) take an `rclcpp::QoS`.
The code picks the right one with `#if RCLCPP_VERSION_MAJOR >= 29`.

### rover_interfaces - message and service definitions

Pure definitions (no code), used by `rover_stm32`. ROS 2 generates C++ and
Python classes from them at build time.

| File | What |
|---|---|
| `msg/FirmwareInfo.msg` | STM32 firmware/boot state (see [8.3](#83-firmwareinfo-what-the-fields-mean)) |
| `msg/FirmwareSlot.msg` | one firmware slot (A or B): valid, version, CRC, size, build time |
| `msg/Stm32Frame.msg` | one raw application message: `cmd`, `seq`, `payload` bytes |
| `srv/GetFirmwareInfo.srv` | ask for the info now |
| `srv/ActivateSlot.srv` | boot slot A or B |
| `srv/UpdateFirmware.srv` | firmware update from a build folder or package |
| `srv/Stm32Request.srv` | send an application command, get the reply |

See a definition: `ros2 interface show rover_interfaces/msg/FirmwareInfo`.

### rover_stm32 - the STM32 link node (Python)

Section 8 explains it in depth. In short: the node `stm32_link` owns the serial
port to the STM32 and offers the STM32's information and commands as ROS topics
and services.

| File | What |
|---|---|
| `rover_stm32/protocol.py` | the wire protocol: framing, CRC, parsing INFO, loading firmware images. No ROS in it, so it is easy to test. |
| `rover_stm32/link.py` | `Stm32Link`: opens the port, background reader thread, request/reply matching, reconnects, the firmware update procedure. No ROS in it either. |
| `rover_stm32/stm32_node.py` | the ROS 2 node: topics, services, parameters. |
| `launch/stm32_link.launch.py` | starts only this node. |
| `systemd/stm32_link.service` | old stand-alone autostart unit. **Not used any more** - `rover.service` starts the node now (see [Known gaps](#13-known-gaps-and-loose-ends)). |
| `test/test_protocol.py` | 19 unit tests for `protocol.py`. |
| `README.md` | short reference for the node. |

---

## 8. The STM32 link in depth

### 8.1 How the Pi and the STM32 talk

The NUCLEO board has an ST-Link debugger built in, which also shows up as a USB
serial port (on the Pi `/dev/ttyACM0`). The STM32 firmware listens on that port
(UART LPUART1, 115200 baud). Both sides speak a small protocol defined in the
firmware repo (`fw_common/fwproto.h`); `protocol.py` is its Python twin, the
same as the firmware's own tool `tools/fwupdate.py`.

Every message (a **frame**) looks like this on the wire:

```
0x00 | COBS( cmd | seq | payload ... | crc32 ) | 0x00
```

- **cmd** - what to do (1 byte). A reply has the same cmd with bit 7 set
  (`cmd | 0x80`), e.g. INFO `0x01` -> reply `0x81`.
- **seq** - a counter the host picks; the STM32 echoes it in the reply, so a
  reply can be matched to its request.
- **payload** - the data. Every **reply** payload starts with a **status byte**:
  `0` OK, `1` unknown command, `2` bad argument, `3` slot in use, `4` flash error,
  `5` verify failed, `6` wrong state.
- **crc32** - checksum over cmd, seq and payload; a damaged frame is dropped and
  the request is retried.
- **COBS** - an encoding that removes every `0x00` byte from the frame, so `0x00`
  can mark where a frame starts/ends. Noise or debug text on the line can never
  be mistaken for a frame.

Commands:

| cmd | Name | Does |
|---|---|---|
| `0x01` | INFO | which slot runs, versions of both slots, boot state, flash layout |
| `0x02` | BEGIN | start writing a firmware image into a slot (erases it) |
| `0x03` | DATA | one chunk (up to 256 bytes) of the image |
| `0x04` | END | finished; the STM32 checks the image's CRC |
| `0x05` | ACTIVATE | boot this slot on trial after the next reset |
| `0x06` | RESET | reboot the STM32 |
| `0x07` | CONFIRM | mark the running image as good |
| `0x40`-`0x7F` | *application* | **free for your own messages** (see 8.6) |

### 8.2 What the node offers

Node name `stm32_link`, so everything is under `/stm32_link/`:

| Name | Kind | What |
|---|---|---|
| `/stm32_link/firmware_info` | topic, `FirmwareInfo` | sent every 2 s; "latched" = a late subscriber gets the last one immediately |
| `/diagnostics` | topic, `DiagnosticArray` | the same in ROS's standard health format (`rqt_robot_monitor` shows it) |
| `/stm32_link/rx` | topic, `Stm32Frame` | messages the STM32 sends by itself, and replies to `tx` |
| `/stm32_link/tx` | topic, `Stm32Frame` | send an application message (0x40-0x7F), no waiting |
| `/stm32_link/get_info` | service | INFO now |
| `/stm32_link/request` | service | send an application command and wait for the reply |
| `/stm32_link/confirm` | service, `std_srvs/Trigger` | mark the running image good |
| `/stm32_link/reset` | service, `std_srvs/Trigger` | reboot the STM32 |
| `/stm32_link/activate` | service | boot slot A or B (e.g. go back to the old firmware) |
| `/stm32_link/update` | service | firmware update |

Parameters:

| Parameter | Default | Meaning |
|---|---|---|
| `port` | *empty* | serial port. Empty = find the board by its USB vendor id (STMicroelectronics, `0x0483`) - it will never pick the Pixhawk's `/dev/ttyAMA0`. `exec:<command>` = talk to a program instead (the simulator, 8.7). |
| `baud` | `115200` | |
| `info_period` | `2.0` | seconds between INFO polls; `0` = only when asked |

Behaviour worth knowing:

- If the USB cable is pulled or the board resets, the node notices, publishes
  `state: disconnected`, and reconnects by itself when the port is back.
- It logs a line whenever the state, running slot or version changes, e.g.
  `STM32 ok: running slot B v0.3.1 (confirmed B, pending -)`.
- **Only one program can use the serial port.** While the node runs,
  `fwupdate.py` / `./fw info-pi` / `./fw deploy-pi` from the firmware repo will
  fail. Stop the node first (`sudo systemctl stop rover` on the Pi) or use the
  node's `update` service.

### 8.3 FirmwareInfo: what the fields mean

```
ros2 topic echo --once /stm32_link/firmware_info
```

| Field | Meaning |
|---|---|
| `connected` | the STM32 answered the last INFO |
| `port` | e.g. `/dev/ttyACM0` |
| `state` | one-word summary, see below |
| `running` | `A`, `B`, or `bootloader` (no valid app) |
| `running_version` | e.g. `0.3.1` |
| `confirmed` | the slot the bootloader trusts (`-` = none) |
| `pending` | a slot waiting to be tried after an update (`-` = none) |
| `attempts` / `max_attempts` | trial boots done for the pending image / limit (3) |
| `slots[]` | both slots: `valid`, `version`, `crc`, `size`, `built` (build time) |
| `slot_a_addr`, `slot_b_addr`, `slot_size` | flash layout (printed as decimal numbers; 134234112 = 0x08004000) |
| `error` | last error text |

`state`:

| state | Means |
|---|---|
| `ok` | running a confirmed image - normal |
| `unconfirmed` | running an image that hasn't confirmed itself yet |
| `trial` | an update is being tried |
| `rejected` | the last update never confirmed - the bootloader **rolled back** to the old one |
| `recovery` | only the bootloader runs, no valid app - send an update |
| `disconnected` | no answer (cable, port busy, board off) |

### 8.4 How a firmware update works (and why it is safe)

The STM32 flash has a **bootloader** and two app **slots, A and B** (54 KB each on
the G431). One slot runs, the other one is free for the next version:

1. INFO: which slot runs? Check the image file was built for this board's layout.
2. BEGIN/DATA/END: write the new image into the **other** slot; the STM32 checks
   its CRC.
3. ACTIVATE + RESET: the bootloader starts the new image **on trial**, with a
   watchdog running.
4. The new firmware confirms itself after 3 s of healthy running.
5. If it crashes or hangs 3 times without confirming, the bootloader goes back to
   the old slot by itself, and INFO shows `rejected`.

So a bad update can't brick the Rover. The `update` service does all of this and
waits for the confirm:

```sh
ros2 service call /stm32_link/update rover_interfaces/srv/UpdateFirmware \
  "{source: '/home/cbm/rover-fw-g431kb-0.3.0.tar.gz'}"
```

- `source` is a path **on the Pi** (the node runs there): a build folder with
  `rover_app_A.bin`/`rover_app_B.bin`, or a release package `.tar.gz` from the
  firmware repo.
- `slot` (optional) forces A or B, `no_reset: true` writes without rebooting,
  `wait_s` is how long to wait for the confirm (default 20).
- **Never update while the Rover drives**: the G431 pauses while it writes flash.

Go back to the other slot by hand:
`ros2 service call /stm32_link/activate rover_interfaces/srv/ActivateSlot "{slot: 'A'}"`.

### 8.5 Raw application messages (0x40-0x7F)

Commands `0x40`-`0x7F` are free for your own data between Pi and STM32 (status,
sensor values, settings...). Two ways to use them from ROS:

```sh
# send and wait for the reply (cmd 64 = 0x40)
ros2 service call /stm32_link/request rover_interfaces/srv/Stm32Request "{cmd: 64, payload: [1, 2]}"

# send without waiting; the reply (and anything the STM32 sends by itself) appears on rx
ros2 topic echo /stm32_link/rx
ros2 topic pub --once /stm32_link/tx rover_interfaces/msg/Stm32Frame "{cmd: 66, payload: [9]}"
```

**Today the firmware handles none of them**, so every such request is answered
with status 1 "unknown command". The protocol works end to end; the messages
just need to be defined.

### 8.6 Adding your own message (e.g. motor status)

Firmware side (rover-firmware, in the app): implement `fwproto_app_command()`.
It runs in the firmware's `fwupdate` task, so replying from there is safe:

```c
#include <string.h>
#include "fwproto.h"

void fwproto_app_command(uint8_t cmd, uint8_t seq, const uint8_t *p, uint32_t len)
{
  if (cmd == 0x40)                          /* STATUS: left/right PWM in microseconds */
  {
    uint8_t out[9] = { FW_OK };             /* status byte first */
    uint32_t l = leftUs, r = rightUs;
    memcpy(&out[1], &l, 4);                 /* little endian */
    memcpy(&out[5], &r, 4);
    fwproto_send(cmd | 0x80U, seq, out, sizeof(out));
    return;
  }
  uint8_t st = FW_ERR_UNKNOWN_CMD;
  fwproto_send(cmd | 0x80U, seq, &st, 1U);
}
```

ROS side: `ros2 service call /stm32_link/request ... "{cmd: 64}"` now returns
those 8 bytes in `payload`. For a nicer interface later, add a message (e.g.
`MotorStatus.msg`) to `rover_interfaces` and a small timer in `stm32_node.py`
that requests `0x40` and publishes the decoded values.

If the STM32 should send messages **by itself** (not as a reply), use `seq = 0`
and protect `fwproto_send()` with a mutex when calling it from other tasks;
they appear on `/stm32_link/rx`.

### 8.7 Testing without the Rover: the simulator

The firmware repo can compile its STM32 code for the PC (`./fw test` builds
`sim_device`). The node can talk to it instead of a real board:

```sh
ros2 run rover_stm32 stm32_link --ros-args \
  -p port:="exec:/path/to/sim_device /tmp/flash.img"
```

`exec:` starts the program and talks to it over stdin/stdout; a RESET ends the
program and the node starts it again (= a reboot). This was used to test updates,
switching slots and the automatic rollback (`sim_device ... --crash-trial` makes
every new image "crash").

---

## 9. Deploying to the Rover: tools/deploy-rover.sh

### 9.1 What it does

```sh
tools/deploy-rover.sh
```

| Step | What happens | If it fails |
|---|---|---|
| 0 | checks it can ssh to `cbm@rover101.local` | stops |
| 1 | **local build**: `colcon build` in `ros_ws` | stops, nothing sent |
| 2 | **local tests**: functional tests must pass; style checks only warn; `rover.launch.py` must load | stops |
| 3 | **upload** `ros_ws/src` to a new folder on the Pi: `~/rover_ws/releases/<date>-<time>-<git sha>[-dirty]` | stops |
| 3 | **build + test on the Pi** (the Pi is ARM, it needs its own build) | stops - **the Rover keeps running the old version** |
| 4 | **activate**: `~/rover_ws/current` -> new release, `previous` -> the old one; old releases are deleted (newest 5 kept) | |
| 4 | **install** `rover.service` if it changed, enable it, disable the old `stm32_link.service` if present, **reboot** - this asks for the Pi's **sudo password** once | stops |
| 4 | waits until the Pi has really rebooted, then shows service state, log, nodes and the STM32 firmware version | shows the log |

`-dirty` in the release name means you had uncommitted changes. Each release has
a `DEPLOY_INFO` file (version, branch, commit, who/when, list of uncommitted
files). `--status` shows it for the active release.

A typical run takes 1-2 minutes plus the reboot. Build output on the Pi is in
`~/rover_ws/releases/<release>/build.out`.

### 9.2 Options

| Option | What |
|---|---|
| *(none)* | full run, ends with a reboot |
| `--build-only` | stop after building and testing on the Pi; nothing changes on the Rover. Good to check that it builds there. |
| `--no-reboot` | activate and only restart `rover.service` (faster than a reboot) |
| `--rollback` | swap `current` and `previous`, reboot. Instant "undo" of the last deploy. |
| `--status` | what is installed/running, plus DEPLOY_INFO |
| `--skip-local` | skip the local build/test (e.g. outside the container) |
| `--lint` | style checks must pass too |
| `--host user@host` | another address, e.g. `--host cbm@192.168.73.186` if mDNS doesn't work. Or set `ROVER_SSH`. |

### 9.3 Why it is built like this

- **Releases + `current` symlink** is the same idea as the STM32's A/B slots: the
  new version is built next to the running one and only switched in once it
  built and passed its tests *on the Pi*. A switch is just a symlink change, and
  `--rollback` is instant.
- **`~/rover` on the Pi is not touched.** That old git checkout has a lot of your
  uncommitted work (GPS, IMU, EKF, Arduino code). The deploy uses its own folder
  `~/rover_ws`.
- **Functional tests block, style checks warn**: the existing packages have
  formatting complaints (flake8/uncrustify/pep257/copyright templates) that say
  nothing about whether the code works. `--lint` makes them block if you want to
  clean them up.
- **charuco_detector is skipped locally** because the container's OpenCV is too
  old (section 7); it is still built and tested on the Pi.

### 9.4 rover.service

`tools/rover.service` is installed as `/etc/systemd/system/rover.service`. It
runs `ros2 launch rover_bringup rover.launch.py` from `~/rover_ws/current`, as
user `cbm`, after the discovery server (`DDS.service`) and MAVROS, with the same
ROS settings as `mavros.service` (`ROS_DISCOVERY_SERVER=127.0.0.1:11811`,
domain 0, Fast DDS). It restarts on crashes, and stops with SIGINT (= Ctrl-C) so
the nodes shut down cleanly.

---

## 10. What runs on the Raspberry Pi

**Name**: `rover101`, reachable as **`rover101.local`** (mDNS) = `192.168.73.186`.
Debian 13 (trixie), ROS 2 Jazzy, user `cbm`.

### Services (start at boot)

| Service | What | Defined where |
|---|---|---|
| `DDS.service` | Fast DDS discovery server, port 11811 | on the Pi only |
| `mavros.service` | MAVROS, Pixhawk on `/dev/ttyAMA0` at 921600 baud, forwards MAVLink to UDP 14550 | on the Pi only |
| `rover.service` | this repo's `rover.launch.py` | `tools/rover.service`, installed by the deploy script |

### Folders in `/home/cbm`

| Folder | What |
|---|---|
| `rover_ws/` | **deployed by this repo**: `releases/`, `current`, `previous`, `rover.service` |
| `rover/` | the older git checkout of this repo with your uncommitted work - left alone |
| `mavros_ws/` | MAVROS build |
| `stm32_ws/` | first, manual install of the STM32 link - **no longer needed**, can be deleted |
| `mavros_params.yaml` | MAVROS settings |

### Serial ports

| Port | Device | Used by |
|---|---|---|
| `/dev/ttyAMA0` | Pixhawk (GPIO UART) | `mavros.service` |
| `/dev/ttyACM0` | NUCLEO's ST-Link (USB) | `stm32_link` in `rover.service` |

### Logging in and looking around

```sh
ssh cbm@rover101.local
systemctl status rover mavros DDS
journalctl -u rover -b            # rover log since the last boot
ls -l ~/rover_ws                  # current/previous releases
cat ~/rover_ws/current/DEPLOY_INFO
```

ROS commands typed in an ssh session on the Pi use the Pi's `~/.bashrc`, which
still loads the **old** `~/rover/ros_ws`, not the deployed one. To use the
deployed packages there: `source ~/rover_ws/current/install/setup.bash`. Easier:
look from your PC with `rover-on`.

---

## 11. Testing

```sh
cd ros_ws
colcon build
colcon test --pytest-args -m "not linter" --ctest-args -LE linter   # functional tests
colcon test-result --verbose                                         # results
colcon test-result --delete-yes                                      # clear old results
```

- **Functional tests** (19 for `rover_stm32/protocol.py`: COBS, framing, CRC,
  INFO parsing, boot states, image checks) - must pass.
- **Style checks** ("linter" tests generated by ROS templates: flake8, pep257,
  copyright, uncrustify, xmllint, mypy) - run with `-m linter --ctest-args -L linter`.
  Several fail in the older packages; they are about formatting, not function.
- `colcon test-result` also counts result files from earlier runs - clear them
  with `--delete-yes` before a run if the numbers look odd.
- Run one package's Python tests directly: `cd ros_ws/src/rover_stm32 && python3 -m pytest test`.
- `deploy-rover.sh` runs all of this for you, here and on the Pi.

---

## 12. Troubleshooting

**`ros2 topic list` only shows `/parameter_events` and `/rosout`**
You are in "off" mode or the daemon has old settings. Run `rover-on`, wait ~5 s,
try again. `rover-status` tells you the mode. Still nothing: is the Pi on
(`ping rover101.local`)? Is `DDS.service` running on the Pi?

**`rover101.local` doesn't resolve**
On the PC: is `avahi-daemon` running? In the container: was it rebuilt after the
mDNS change (`getent hosts rover101.local` must print an address)? Workaround:
use the IP, e.g. `--host cbm@192.168.73.186`.

**`ros2 run`: "Package '...' not found"**
`source ros_ws/install/setup.bash` in this terminal, and check the build
succeeded.

**colcon: "CMakeCache.txt directory ... is different"**
The `build/` folder was made when the repo was somewhere else. Delete the
generated folders and rebuild: `rm -rf ros_ws/build ros_ws/install ros_ws/log`.

**charuco_detector fails to build in the container ("OpenCV ... 4.7")**
Expected: the container has OpenCV 4.6. Build the rest with
`colcon build --packages-skip charuco_detector`; it is built on the Pi.

**`fwupdate.py` / `./fw deploy-pi` fails with no answer from the STM32**
`stm32_link` holds `/dev/ttyACM0`. On the Pi: `sudo systemctl stop rover`, do
the update, `sudo systemctl start rover`. Or use the `/stm32_link/update` service.

**The STM32 shows `disconnected`**
USB cable? `ls /dev/serial/by-id/` on the Pi should show an `STMicroelectronics_STLINK`
entry. Is something else using the port (`fuser /dev/ttyACM0`)?

**The deploy stops at "the new version failed on the Pi"**
Nothing changed on the Rover. Read the output above it, or
`~/rover_ws/releases/<release>/build.out` on the Pi.

**After a deploy the Rover misbehaves**
`tools/deploy-rover.sh --rollback`.

**Camera window doesn't open (py_viewer, rqt)**
Run `xhost +local:` on the PC (not in the container), then try again.

---

## 13. Known gaps and loose ends

Things that are not finished or are worth knowing before you change something:

1. **The STM32 firmware has no application messages yet.** Version/boot info
   works; "other status" (motor PWM, etc.) needs firmware code first (8.6).
2. **`charuco_detector` gets no `CameraInfo`.** The camera node publishes only the
   compressed image. Until something publishes the camera calibration (e.g. from
   `calibrate_charuco.py`'s result), no pose comes out.
3. **The Pi's old `~/rover` launch file conflicts with MAVROS.** Its uncommitted
   `rover.launch.py` starts `arduino_com` (Arduino is no longer part of the Rover)
   and the GPS driver on `/dev/ttyAMA0`, the Pixhawk's port. Don't start it while
   `mavros.service` runs. GPS/IMU/EKF from there are not in this repo yet.
4. **Firmware deploys from the rover-firmware repo collide with `stm32_link`**
   (`./fw deploy-pi` and the GitHub deploy job use `/dev/ttyACM0` too). They
   should stop `rover.service` before and start it after - not done yet.
5. **`ros_ws/src/rover_stm32/systemd/stm32_link.service` is obsolete**: the node
   now runs inside `rover.service`. The deploy script disables the old unit if it
   was ever installed. `~/stm32_ws` on the Pi can be deleted.
6. **Style check failures** in `cpp_pubsub`, `charuco_detector`, `py_viewer` and
   `rover_bringup/setup.py` (formatting, import order, copyright templates).
7. **`run.sh`** builds and launches from `/home/cbm/rover/ros_ws` (the Pi's old
   folder). `tools/deploy-rover.sh` + `rover.service` replace it.
8. **The Pi's `~/.bashrc`** loads the old `~/rover/ros_ws` (section 10).
9. **`ament_mypy` isn't installed** (container nor Pi), so `py_viewer`'s mypy
   check is skipped.

### Changes made to existing code (for reference)

| Where | Change | Why |
|---|---|---|
| `cpp_pubsub/CMakeLists.txt` | needs OpenCV `4` instead of `4.7` | it only uses basic OpenCV; lets it build in the container |
| `charuco_detector/src/charuco_detector_node.cpp` | QoS for the CameraInfo subscriber chosen by ROS version | didn't compile on the Pi's current Jazzy |
| `py_viewer/test/test_mypy.py` | skips if `ament_mypy` is missing | it broke the whole test run |
| `rover_bringup/setup.py` | declares `pytest` for tests | colcon used `unittest` and ran nothing |
| `rover_bringup/launch/rover.launch.py` | starts `stm32_link` too | |
| `.gitignore` | rewritten for ROS 2 | the old ROS 1 template could hide real files like `msg/*Goal.msg` |

---

## 14. Glossary

| Word | Meaning |
|---|---|
| **ament_cmake / ament_python** | the two kinds of ROS 2 package: C++ (CMake) or Python (setup.py) |
| **Avahi / mDNS** | lets computers find each other by `<name>.local` without a DNS server |
| **bootloader** | small program at the start of the STM32 flash that picks which app slot to start |
| **colcon** | the ROS 2 build tool |
| **COBS** | byte encoding that removes `0x00` so it can mark frame boundaries |
| **CRC32** | checksum to detect damaged data |
| **DDS / Fast DDS** | the network layer ROS 2 nodes use to find and talk to each other |
| **discovery server** | a central program nodes register with, instead of multicast |
| **dev container** | Docker container VS Code opens the project in |
| **latched topic** | (transient local QoS) a new subscriber gets the last message immediately |
| **MAVLink / MAVROS** | the Pixhawk's protocol / the ROS bridge for it |
| **QoS** | delivery settings of a topic (reliable vs best effort, history...) |
| **release / current / previous** | deploy folders on the Pi (section 9) |
| **slot A / B** | the STM32's two firmware places (section 8.4) |
| **ST-Link** | the debugger on the NUCLEO board; also gives the USB serial port |
| **systemd unit / service** | Linux's way to start programs at boot (`systemctl`, `journalctl`) |
| **topic / service / node / parameter** | see section 4 |

---

## Notes (original)

Når man kører ros2 over wifi, er der nogle gange brug for 
en fast DDS server da multicast ikke altid fungerer
så godt over wifi, kablet er fint men wifi er skrald.
for at starte en dds server på den pågældende maskine brug

`fastdds discovery -i 0 -p 11811`

For så at få forbindelse til den DDS server, brug

`export ROS_DISCOVERY_SERVER=192.168.73.141:11811`

selvfølgelig med den ip som dds serveren ligger på
ikke rode ved porten.

DDS-serveren kører på Pi'en (DDS.service), som kan findes med mDNS som `rover101.local`:

`export ROS_DISCOVERY_SERVER=rover101.local:11811`

`export ROS_SUPER_CLIENT=TRUE` (så `ros2 topic list` m.m. ser alle noder)

`ros2 topic list --no-daemon --spin-time 8` (giv discovery et par sekunder)



Der er åbenbart en flaskehals når man skal køre med højere opløsning og framerate.
Man kan sætte miljøvariablen FASTDDS_BUILTIN_TRANSPORTS=UDPv4 for at bruge UDP i stedet for TCP, hvilket kan give bedre performance.

`export FASTDDS_BUILTIN_TRANSPORTS=UDPv4`

To make the rover move with full speed:

`ros2 topic pub -1 /motor_speed std_msgs/msg/UInt8 "{data: 255}"`
