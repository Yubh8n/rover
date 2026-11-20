# rover_stm32

ROS 2 node for the serial link between the Raspberry Pi 5 and the STM32
(NUCLEO-G431KB). It speaks the same protocol as `tools/fwupdate.py` in
[rover-firmware](https://github.com/Yubh8n/rover-firmware) (`fw_common/fwproto.h`):
COBS frames with a CRC-32, `cmd | seq | payload`, replies use `cmd | 0x80`.

The node owns the serial port. **Stop it before you run `fwupdate.py` / `./fw info-pi`**,
or do the update through the node's `~/update` service instead.

```sh
ros2 run rover_stm32 stm32_link                       # finds the Nucleo's ST-Link by itself
ros2 run rover_stm32 stm32_link --ros-args -p port:=/dev/ttyACM0
ros2 launch rover_stm32 stm32_link.launch.py          # or as part of rover_bringup/rover.launch.py
```

## Interface

| Name | Type | What |
|---|---|---|
| `~/firmware_info` | `rover_interfaces/FirmwareInfo` (topic, latched) | running slot + version, confirmed/pending slot, both slots' versions, `state`, every `info_period` s |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` | the same, for `rqt_robot_monitor` |
| `~/rx` | `rover_interfaces/Stm32Frame` (topic) | frames the STM32 sends by itself, and replies to `~/tx` |
| `~/tx` | `rover_interfaces/Stm32Frame` (topic) | send an app frame (cmd `0x40..0x7F`), no waiting |
| `~/get_info` | `rover_interfaces/GetFirmwareInfo` | INFO now |
| `~/request` | `rover_interfaces/Stm32Request` | app command `0x40..0x7F`, waits for the reply |
| `~/confirm` / `~/reset` | `std_srvs/Trigger` | mark the running image good / reboot the STM32 |
| `~/activate` | `rover_interfaces/ActivateSlot` | boot slot A or B on trial (go back to the old image) |
| `~/update` | `rover_interfaces/UpdateFirmware` | firmware update into the other slot, reboot, wait for the confirm; rollback is reported as a failure |

`state` is `ok`, `unconfirmed`, `trial`, `rejected` (update rolled back), `recovery`
(only the bootloader runs) or `disconnected`.

```sh
ros2 topic echo /stm32_link/firmware_info
ros2 service call /stm32_link/update rover_interfaces/srv/UpdateFirmware \
     "{source: '/home/cbm/rover-fw-g431kb-0.3.0.tar.gz'}"
ros2 service call /stm32_link/activate rover_interfaces/srv/ActivateSlot "{slot: 'A'}"
ros2 service call /stm32_link/request rover_interfaces/srv/Stm32Request "{cmd: 64}"
```

The G431 pauses while its flash is written: **don't update while the Rover is driving.**

## Own status messages (firmware side)

Commands `0x40..0x7F` are free. Implement `fwproto_app_command()` in the app
(it runs in the `fwupdate` task, so replying with `fwproto_send()` is safe there):

```c
#include "fwproto.h"

void fwproto_app_command(uint8_t cmd, uint8_t seq, const uint8_t *p, uint32_t len)
{
  if (cmd == 0x40)                       /* STATUS: left/right PWM in microseconds */
  {
    uint8_t out[9] = { FW_OK };
    memcpy(&out[1], (const void *)&leftUs, 4);
    memcpy(&out[5], (const void *)&rightUs, 4);
    fwproto_send(cmd | 0x80U, seq, out, sizeof(out));
    return;
  }
  uint8_t st = FW_ERR_UNKNOWN_CMD;
  fwproto_send(cmd | 0x80U, seq, &st, 1U);
}
```

Then `~/request` with `cmd: 64` returns the 8 bytes in `payload`. If the STM32
should send frames on its own (from other tasks), protect `fwproto_send()` with a
mutex, use `seq = 0`, and they appear on `~/rx`.

## Testing without hardware

The node talks to the firmware's PC simulator with `port:=exec:<command>`:

```sh
# in rover-firmware: ./fw test builds build/<env>/host-test/g431kb/sim_device
ros2 run rover_stm32 stm32_link --ros-args \
     -p port:="exec:/path/to/sim_device /tmp/flash.img"
```

Unit tests: `python3 -m pytest test` in this folder.
