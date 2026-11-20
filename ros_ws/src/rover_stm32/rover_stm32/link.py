"""
Stm32Link - owns the serial port to the STM32 (no ROS in here).

A reader thread parses every incoming frame:
  - the reply to the request in flight (cmd | 0x80, same seq) wakes up request()
  - everything else (frames the STM32 sends on its own, late replies) goes to on_frame()

If the port disappears (USB unplugged, STM32 reset re-enumerating), the reader
closes it and opens it again until it is back.
"""
import glob
import os
import select
import shlex
import struct
import subprocess
import threading
import time

from . import protocol as p

ST_USB_VID = 0x0483   # STMicroelectronics: ST-Link virtual COM port and STM32 USB serial


def find_st_ports():
    """Serial ports that belong to an ST USB device (the Nucleo's ST-Link)."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return sorted(glob.glob('/dev/serial/by-id/*STM*') + glob.glob('/dev/serial/by-id/*STLink*'))
    return [d.device for d in sorted(list_ports.comports(), key=lambda d: d.device)
            if d.vid == ST_USB_VID]


def resolve_port(port):
    """'' = the one connected ST board (like fwupdate.py), else the given port."""
    if port:
        return port
    ports = find_st_ports()
    if len(ports) == 1:
        return ports[0]
    if len(ports) > 1:
        raise p.FwError('several ST boards found (%s) - set the port parameter' % ', '.join(ports))
    raise p.FwError('no STM32 / ST-Link serial port found - is the board plugged in?')


class SerialTransport:
    def __init__(self, port, baud):
        import serial
        self.serial_exc = serial.SerialException
        try:
            self.ser = serial.Serial(port, baud, timeout=0.1, write_timeout=1.0)
        except (serial.SerialException, OSError) as e:
            raise p.FwError('cannot open %s: %s' % (port, getattr(e, 'strerror', None) or e))
        self.ser.reset_input_buffer()

    def write(self, data):
        try:
            self.ser.write(data)
            self.ser.flush()
        except (self.serial_exc, OSError) as e:
            raise p.FwError('write failed: %s' % e)

    def read(self):
        """Blocks up to 0.1 s. Raises FwError if the port is gone."""
        try:
            first = self.ser.read(1)
            return first + self.ser.read(self.ser.in_waiting) if first else b''
        except (self.serial_exc, OSError, TypeError) as e:
            raise p.FwError('read failed: %s' % e)

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass


class ExecTransport:
    """port 'exec:<command>': talk to a program over stdin/stdout, e.g. the PC
    simulator of the STM32 (rover-firmware fw_common/test/sim_device). The program
    exits on RESET and is started again on the next read/write = reboot."""

    def __init__(self, cmd):
        self.cmd = shlex.split(cmd)
        self.proc = None
        self.lock = threading.Lock()

    def _ensure(self):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self.proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            return self.proc

    def write(self, data):
        proc = self._ensure()
        try:
            proc.stdin.write(data)
            proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass

    def read(self):
        proc = self._ensure()
        r, _, _ = select.select([proc.stdout], [], [], 0.1)
        if not r:
            return b''
        data = os.read(proc.stdout.fileno(), 4096)
        if not data:              # program exited (simulated reset)
            proc.wait()
            time.sleep(0.05)
        return data

    def close(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait()


def open_transport(port, baud):
    if port.startswith('exec:'):
        return ExecTransport(port[5:])
    return SerialTransport(port, baud)


class Stm32Link:
    def __init__(self, port='', baud=115200, on_frame=None, log=None):
        self.port_param = port
        self.baud = baud
        self.on_frame = on_frame or (lambda cmd, seq, payload: None)
        self.log = log or (lambda level, msg: None)
        self.port = ''               # resolved port in use
        self.error = ''

        self._tr = None
        self._tr_lock = threading.Lock()
        self._req_lock = threading.Lock()   # one request at a time
        self._pending = None                # (reply cmd, seq)
        self._reply = None
        self._reply_event = threading.Event()
        self._seq = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._reader, name='stm32-reader', daemon=True)

    # -------------------------------------------------------------- lifecycle
    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2.0)
        self._close()

    @property
    def is_open(self):
        return self._tr is not None

    def _open(self):
        port = resolve_port(self.port_param)
        tr = open_transport(port, self.baud)
        with self._tr_lock:
            self._tr = tr
        self.port = port
        self.error = ''
        self.log('info', 'STM32 link open on %s' % port)

    def _close(self):
        with self._tr_lock:
            tr, self._tr = self._tr, None
        if tr:
            tr.close()

    def _reader(self):
        parser = p.FrameParser()
        last_err = None
        while not self._stop.is_set():
            if self._tr is None:
                try:
                    self._open()
                    parser = p.FrameParser()
                    last_err = None
                except p.FwError as e:
                    self.error = str(e)
                    if str(e) != last_err:          # log each new problem once
                        self.log('warn', str(e))
                        last_err = str(e)
                    self._stop.wait(1.0)
                    continue
            try:
                data = self._tr.read()
            except p.FwError as e:
                self.error = 'link lost on %s: %s' % (self.port, e)
                self.log('warn', self.error)
                self._close()
                continue
            for cmd, seq, payload in parser.feed(data):
                pend = self._pending
                if pend and cmd == pend[0] and seq == pend[1]:
                    self._reply = payload
                    self._reply_event.set()
                else:
                    try:
                        self.on_frame(cmd, seq, payload)
                    except Exception as e:  # never let a callback kill the reader
                        self.log('error', 'on_frame callback failed: %s' % e)

    # ---------------------------------------------------------------- sending
    def _next_seq(self):
        self._seq = (self._seq + 1) & 0xFF
        if self._seq == 0:             # seq 0 is left for frames the STM32 sends by itself
            self._seq = 1
        return self._seq

    def _write(self, frame):
        with self._tr_lock:
            tr = self._tr
        if tr is None:
            raise p.FwError('STM32 not connected%s' % (' (%s)' % self.error if self.error else ''))
        tr.write(frame)

    def send(self, cmd, payload=b'', seq=None):
        """Fire and forget. A reply (if any) arrives through on_frame."""
        with self._req_lock:
            self._write(p.encode_frame(cmd, self._next_seq() if seq is None else seq, payload))

    def request_raw(self, cmd, payload=b'', timeout=1.0, retries=3):
        """Send cmd and wait for its reply -> (status, payload after status).
        Raises FwError if there is no reply."""
        with self._req_lock:
            seq = self._next_seq()
            frame = p.encode_frame(cmd, seq, payload)
            self._reply_event.clear()
            self._pending = ((cmd | p.REPLY) & 0xFF, seq)
            try:
                for _ in range(max(1, retries)):
                    self._write(frame)
                    if self._reply_event.wait(timeout):
                        rsp = self._reply
                        if not rsp:
                            raise p.FwError('empty reply to command 0x%02X' % cmd)
                        return rsp[0], bytes(rsp[1:])
            finally:
                self._pending = None
            raise p.FwError('no answer to command 0x%02X - wrong port/baud, or STM32 not '
                            'running the protocol?' % cmd)

    def request(self, cmd, payload=b'', timeout=1.0, retries=3):
        """Like request_raw, but a non-OK status raises FwError."""
        status, data = self.request_raw(cmd, payload, timeout, retries)
        if status != 0:
            raise p.FwError('command 0x%02X failed: %s' % (cmd, p.STATUS.get(status, status)), status)
        return data

    # ------------------------------------------------------- firmware commands
    def info(self, timeout=2.0, retries=1):
        return p.parse_info(self.request(p.CMD_INFO, timeout=timeout, retries=retries))

    def confirm(self):
        self.request(p.CMD_CONFIRM)

    def reset(self):
        self.request(p.CMD_RESET, timeout=2.0)

    def activate(self, slot):
        self.request(p.CMD_ACTIVATE, bytes([slot]), timeout=5.0)

    def wait_for(self, cond, timeout):
        """Poll INFO until cond(info) is true -> last info (None if nothing answered)."""
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline and not self._stop.is_set():
            try:
                last = self.info(timeout=1.0)
                if cond(last):
                    return last
            except p.FwError:
                pass
            time.sleep(0.5)
        return last

    def update(self, source, slot=None, no_reset=False, wait=20, progress=None):
        """Same flow as `fwupdate.py update`. Returns (version, slot) on success,
        raises FwError otherwise (incl. "rolled back")."""
        say = progress or (lambda msg: None)
        info = self.info()
        running = info['running']
        target = slot if slot is not None else (0 if running == p.SLOT_NONE else 1 - running)
        if target == running:
            raise p.FwError('cannot write slot %s - it is running' % 'AB'[target])

        data, version = p.load_image(source, target, info['slot_base'][target], info['slot_size'])
        now = 'bootloader' if running == p.SLOT_NONE else 'slot ' + p.SLOT_NAMES[running]
        say('running %s -> writing v%s to slot %s (%d bytes)'
            % (now, p.fmt_version(version), 'AB'[target], len(data)))

        say('erasing slot %s ...' % 'AB'[target])
        self.request(p.CMD_BEGIN, struct.pack('<B3xI', target, len(data)), timeout=20.0)
        t0 = time.monotonic()
        last_q = -1
        for off in range(0, len(data), p.MAX_DATA):
            self.request(p.CMD_DATA, struct.pack('<I', off) + data[off:off + p.MAX_DATA],
                         timeout=1.0, retries=5)
            q = 4 * min(off + p.MAX_DATA, len(data)) // len(data)
            if q != last_q:
                say('writing %3d%%' % (25 * q))
                last_q = q
        say('write done (%.1f s)' % (time.monotonic() - t0))

        self.request(p.CMD_END, timeout=5.0)
        say('verified on target (CRC ok)')
        self.activate(target)
        say('slot %s activated for a trial boot' % 'AB'[target])
        if no_reset:
            say('not resetting (no_reset) - it boots on the next reset')
            return version, target

        self.reset()
        say('rebooting, waiting for the new image to confirm itself ...')
        time.sleep(1.0)

        def settled(i):
            ok = i['running'] == target and i['confirmed'] == target and i['pending'] == p.SLOT_NONE
            rejected = (i['pending'] == target and i['attempts'] >= i['max_attempts']
                        and i['running'] != target)
            return ok or rejected

        final = self.wait_for(settled, wait)
        if final and final['running'] == target and final['confirmed'] == target:
            say('SUCCESS: running v%s from slot %s (confirmed)' % (p.fmt_version(version), 'AB'[target]))
            return version, target
        if final and final['pending'] == target and final['attempts'] >= final['max_attempts']:
            raise p.FwError('the new image never confirmed itself (crash or hang) - the bootloader '
                            'ROLLED BACK to slot %s' % p.SLOT_NAMES.get(final['running'], '?'))
        raise p.FwError('update did not confirm within %d s - the bootloader rolls back after '
                        '%d failed boots' % (wait, final['max_attempts'] if final else 3))
