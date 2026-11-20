"""
stm32_link - ROS 2 node for the serial link between the Raspberry Pi and the STM32.

Speaks the same protocol as tools/fwupdate.py in rover-firmware (fw_common/fwproto.h),
and is the only process that may hold the port (stop it before running fwupdate.py).

Topics
  ~/firmware_info  rover_interfaces/FirmwareInfo  version + boot state (latched, every info_period)
  /diagnostics     diagnostic_msgs/DiagnosticArray  same, for rqt_robot_monitor
  ~/rx             rover_interfaces/Stm32Frame    frames the STM32 sends on its own (0x40..0x7F)
  ~/tx             rover_interfaces/Stm32Frame    send an app frame to the STM32 (no reply wait)

Services
  ~/get_info  rover_interfaces/GetFirmwareInfo   INFO now
  ~/request   rover_interfaces/Stm32Request      app command 0x40..0x7F, wait for the reply
  ~/confirm   std_srvs/Trigger                   mark the running image good
  ~/reset     std_srvs/Trigger                   reboot the STM32
  ~/activate  rover_interfaces/ActivateSlot      boot slot A/B on trial
  ~/update    rover_interfaces/UpdateFirmware    firmware update (NOT while driving)

Parameters
  port         ''      serial port; '' = find the ST-Link automatically,
                       'exec:<cmd>' = PC simulator (rover-firmware fw_common/test/sim_device)
  baud         115200
  info_period  2.0     seconds between INFO polls (0 = only on request)
"""
import signal
import threading

import rclpy
from builtin_interfaces.msg import Time
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Header
from std_srvs.srv import Trigger

from rover_interfaces.msg import FirmwareInfo, FirmwareSlot, Stm32Frame
from rover_interfaces.srv import ActivateSlot, GetFirmwareInfo, Stm32Request, UpdateFirmware

from . import protocol as p
from .link import Stm32Link

DIAG_LEVEL = {'ok': DiagnosticStatus.OK, 'unconfirmed': DiagnosticStatus.WARN,
              'trial': DiagnosticStatus.WARN, 'rejected': DiagnosticStatus.WARN,
              'recovery': DiagnosticStatus.ERROR, 'disconnected': DiagnosticStatus.ERROR}


def slot_from_name(name):
    name = (name or '').strip().upper()
    if name not in ('A', 'B'):
        raise p.FwError("slot must be 'A' or 'B', got '%s'" % name)
    return 'AB'.index(name)


class Stm32Node(Node):
    def __init__(self):
        super().__init__('stm32_link')
        self.declare_parameter('port', '')
        self.declare_parameter('baud', 115200)
        self.declare_parameter('info_period', 2.0)

        self.link = Stm32Link(port=self.get_parameter('port').value,
                              baud=self.get_parameter('baud').value,
                              on_frame=self._on_frame, log=self._log)
        self._busy = threading.Lock()   # held during an update: no INFO polls in between
        self._last_state = None

        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.pub_info = self.create_publisher(FirmwareInfo, '~/firmware_info', latched)
        self.pub_diag = self.create_publisher(DiagnosticArray, '/diagnostics', 10)
        self.pub_rx = self.create_publisher(Stm32Frame, '~/rx', 50)
        self.create_subscription(Stm32Frame, '~/tx', self._on_tx, 50)

        # Short services and the poll timer may run while an update service call is busy.
        cb = ReentrantCallbackGroup()
        self.create_service(GetFirmwareInfo, '~/get_info', self._srv_get_info, callback_group=cb)
        self.create_service(Stm32Request, '~/request', self._srv_request, callback_group=cb)
        self.create_service(Trigger, '~/confirm', self._srv_confirm, callback_group=cb)
        self.create_service(Trigger, '~/reset', self._srv_reset, callback_group=cb)
        self.create_service(ActivateSlot, '~/activate', self._srv_activate, callback_group=cb)
        self.create_service(UpdateFirmware, '~/update', self._srv_update,
                            callback_group=MutuallyExclusiveCallbackGroup())

        period = float(self.get_parameter('info_period').value)
        if period > 0:
            self.create_timer(period, self._poll, callback_group=MutuallyExclusiveCallbackGroup())

        self.link.start()

    # ------------------------------------------------------------------ helpers
    def _log(self, level, msg):
        # rclpy ties the severity to the calling line, so one call site per level
        if level == 'error':
            self.get_logger().error(msg)
        elif level == 'warn':
            self.get_logger().warn(msg)
        else:
            self.get_logger().info(msg)

    def _info_msg(self, info=None, error=''):
        m = FirmwareInfo()
        m.stamp = self.get_clock().now().to_msg()
        m.port = self.link.port
        m.error = error or ('' if info else self.link.error)
        if info is None:
            m.connected = False
            m.state = 'disconnected'
            return m
        m.connected = True
        m.state = p.info_state(info)
        m.protocol_version = info['proto']
        m.running = 'bootloader' if info['running'] == p.SLOT_NONE else p.SLOT_NAMES[info['running']]
        m.confirmed = p.SLOT_NAMES.get(info['confirmed'], '?')
        m.pending = p.SLOT_NAMES.get(info['pending'], '?')
        m.attempts = info['attempts']
        m.max_attempts = info['max_attempts']
        for idx, s in enumerate(info['slots']):
            fs = FirmwareSlot(name='AB'[idx], valid=s['valid'])
            if s['valid']:
                fs.version = p.fmt_version(s['version'])
                fs.version_raw = s['version']
                fs.crc = s['crc']
                fs.size = s['size']
                fs.built = Time(sec=s['built'])
            m.slots.append(fs)
            if idx == info['running'] and s['valid']:
                m.running_version = fs.version
        m.slot_a_addr, m.slot_b_addr = info['slot_base']
        m.slot_size = info['slot_size']
        return m

    def _publish(self, m):
        self.pub_info.publish(m)

        st = DiagnosticStatus(name='stm32: firmware', hardware_id=m.port or 'stm32',
                              level=DIAG_LEVEL.get(m.state, DiagnosticStatus.WARN))
        st.message = m.state if not m.running_version else '%s, v%s slot %s' % (
            m.state, m.running_version, m.running)
        kv = [('state', m.state), ('running', m.running), ('version', m.running_version),
              ('confirmed', m.confirmed), ('pending', m.pending),
              ('attempts', '%d/%d' % (m.attempts, m.max_attempts)), ('error', m.error)]
        kv += [('slot %s' % s.name, ('v%s crc %08X' % (s.version, s.crc)) if s.valid else 'empty')
               for s in m.slots]
        st.values = [KeyValue(key=k, value=str(v)) for k, v in kv]
        self.pub_diag.publish(DiagnosticArray(header=Header(stamp=m.stamp), status=[st]))

        key = (m.state, m.running, m.running_version)
        if key != self._last_state:
            text = 'STM32 %s' % m.state
            if m.state == 'recovery':
                text += ': only the bootloader runs - send an update'
            elif m.connected:
                text += ': running slot %s v%s (confirmed %s, pending %s)' % (
                    m.running, m.running_version or '?', m.confirmed, m.pending)
            if m.state == 'ok':
                self.get_logger().info(text)
            else:
                self.get_logger().warn(text)
            self._last_state = key

    def _query(self):
        """INFO -> FirmwareInfo (published), never raises."""
        try:
            m = self._info_msg(self.link.info())
        except p.FwError as e:
            m = self._info_msg(None, '' if not self.link.is_open else str(e))
        self._publish(m)
        return m

    # ---------------------------------------------------------------- callbacks
    def _poll(self):
        if self._busy.acquire(blocking=False):
            try:
                self._query()
            finally:
                self._busy.release()

    def _on_frame(self, cmd, seq, payload):
        self.pub_rx.publish(Stm32Frame(cmd=cmd, seq=seq, payload=list(payload)))

    def _on_tx(self, msg):
        if not p.CMD_APP_FIRST <= msg.cmd <= p.CMD_APP_LAST:
            self.get_logger().warn('~/tx: cmd 0x%02X refused - only 0x40..0x7F (use the services '
                                   'for firmware commands)' % msg.cmd)
            return
        if self._busy.locked():
            self.get_logger().warn('~/tx: dropped, firmware update in progress')
            return
        try:
            self.link.send(msg.cmd, bytes(msg.payload))
        except p.FwError as e:
            self.get_logger().warn('~/tx: %s' % e)

    def _guarded(self, res, fn):
        """Run fn() unless an update is running; fill res.success/message."""
        if not self._busy.acquire(blocking=False):
            res.success, res.message = False, 'firmware update in progress'
            return res
        try:
            res.message = fn() or 'ok'
            res.success = True
        except p.FwError as e:
            res.success, res.message = False, str(e)
        finally:
            self._busy.release()
        return res

    def _srv_get_info(self, req, res):
        def run():
            res.info = self._info_msg(self.link.info())
            self._publish(res.info)
        self._guarded(res, run)
        if not res.success and not res.info.state:
            res.info = self._info_msg(None, res.message)
        return res

    def _srv_request(self, req, res):
        res.status = 255
        if not p.CMD_APP_FIRST <= req.cmd <= p.CMD_APP_LAST:
            res.success, res.message = False, 'cmd must be 0x40..0x7F (application commands)'
            return res

        def run():
            status, data = self.link.request_raw(req.cmd, bytes(req.payload),
                                                 timeout=req.timeout or 1.0, retries=1)
            res.status, res.payload = status, list(data)
            if status != 0:
                raise p.FwError(p.STATUS.get(status, 'status %d' % status), status)
        return self._guarded(res, run)

    def _srv_confirm(self, req, res):
        return self._guarded(res, lambda: (self.link.confirm(), 'running image confirmed')[1])

    def _srv_reset(self, req, res):
        return self._guarded(res, lambda: (self.link.reset(), 'STM32 reset')[1])

    def _srv_activate(self, req, res):
        def run():
            slot = slot_from_name(req.slot)
            self.link.activate(slot)
            if req.no_reset:
                return 'slot %s boots on trial after the next reset' % 'AB'[slot]
            self.link.reset()
            return 'slot %s activated, STM32 reset' % 'AB'[slot]
        return self._guarded(res, run)

    def _srv_update(self, req, res):
        log = self.get_logger()
        if not self._busy.acquire(blocking=False):
            res.success, res.message = False, 'another firmware command is running'
            return res
        try:
            log.warn('firmware update from %s - do not drive the Rover until it is done' % req.source)
            slot = slot_from_name(req.slot) if req.slot.strip() else None
            version, target = self.link.update(req.source, slot, req.no_reset,
                                               req.wait_s or 20, progress=log.info)
            res.success = True
            res.version, res.slot = p.fmt_version(version), 'AB'[target]
            res.message = ('v%s written to slot %s%s' % (res.version, res.slot,
                           ' (boots on next reset)' if req.no_reset else ', running and confirmed'))
        except p.FwError as e:
            res.success, res.message = False, str(e)
            log.error('firmware update failed: %s' % e)
        finally:
            self._busy.release()
        self._query()
        return res

    def destroy_node(self):
        self.link.stop()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = Stm32Node()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        # ros2 launch forwards Ctrl-C, so a second SIGINT often follows the
        # first one: don't let it interrupt the cleanup (traceback, port left open)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
