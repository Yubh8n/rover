"""
STM32 link protocol (no ROS in here).

Mirror of fw_common/fwproto.h and tools/fwupdate.py in the rover-firmware repo:

    wire:  0x00 | COBS( cmd | seq | payload... | crc32 ) | 0x00
    cmd:   command id, replies use cmd | 0x80
    seq:   echoed in the reply
    crc32: little endian zlib CRC-32 over cmd, seq and payload

Every reply payload starts with a status byte (STATUS below).
"""
import os
import struct
import tarfile
import zlib

# --- commands (fw_common/fwproto.h) -----------------------------------------
CMD_INFO = 0x01
CMD_BEGIN = 0x02
CMD_DATA = 0x03
CMD_END = 0x04
CMD_ACTIVATE = 0x05
CMD_RESET = 0x06
CMD_CONFIRM = 0x07
CMD_APP_FIRST = 0x40       # 0x40..0x7F: free for Rover messages
CMD_APP_LAST = 0x7F
REPLY = 0x80

STATUS = {0: 'OK', 1: 'unknown command', 2: 'bad argument', 3: 'slot is in use (running)',
          4: 'flash error', 5: 'verify failed', 6: 'wrong state'}
MAX_DATA = 256             # FWPROTO_MAX_DATA
MAX_PAYLOAD = MAX_DATA + 8  # FWPROTO_MAX_PAYLOAD

SLOT_NONE = 0xFF
SLOT_NAMES = {0: 'A', 1: 'B', SLOT_NONE: '-'}

# --- image layout (fw_common/image_header.h, boot_layout.h) ------------------
IMAGE_MAGIC = 0x52564F52   # "ROVR"
IMAGE_HEADER_SIZE = 0x200
HEADER_FMT = '<7I8I16sI'


class FwError(Exception):
    """Protocol error. status is the STM32 status byte, or None (no reply / local error)."""

    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


# --- COBS ---------------------------------------------------------------------
def cobs_encode(data):
    out = bytearray(b'\0')
    code_pos, code = 0, 1
    for b in data:
        if b == 0:
            out[code_pos] = code
            code_pos, code = len(out), 1
            out.append(0)
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_pos] = code
                code_pos, code = len(out), 1
                out.append(0)
    out[code_pos] = code
    return bytes(out)


def cobs_decode(data):
    out, i = bytearray(), 0
    while i < len(data):
        code = data[i]
        i += 1
        if code == 0 or i + code - 1 > len(data):
            return None
        out += data[i:i + code - 1]
        i += code - 1
        if code != 0xFF and i < len(data):
            out.append(0)
    return bytes(out)


# --- frames -------------------------------------------------------------------
def encode_frame(cmd, seq, payload=b''):
    if len(payload) > MAX_PAYLOAD:
        raise FwError('payload too long (%d > %d bytes)' % (len(payload), MAX_PAYLOAD))
    body = bytes([cmd & 0xFF, seq & 0xFF]) + bytes(payload)
    return b'\0' + cobs_encode(body + struct.pack('<I', zlib.crc32(body))) + b'\0'


class FrameParser:
    """Feed raw bytes, get (cmd, seq, payload) for every valid frame.
    Anything else on the line (debug printf text, noise) is dropped."""

    def __init__(self):
        self.buf = bytearray()

    def feed(self, data):
        self.buf += data
        frames = []
        while b'\0' in self.buf:
            i = self.buf.index(b'\0')
            enc = bytes(self.buf[:i])
            del self.buf[:i + 1]
            if not enc:
                continue
            raw = cobs_decode(enc)
            if raw is None or len(raw) < 6:
                continue
            body, crc = raw[:-4], struct.unpack('<I', raw[-4:])[0]
            if zlib.crc32(body) == crc:
                frames.append((body[0], body[1], body[2:]))
        if len(self.buf) > 4096:        # no delimiter for ages: not our protocol
            del self.buf[:-1024]
        return frames


# --- INFO ---------------------------------------------------------------------
def fmt_version(v):
    return '%d.%d.%d' % (v >> 16, (v >> 8) & 0xFF, v & 0xFF)


def parse_version(s):
    major, minor, patch = (int(x) for x in s.split('.'))
    return (major << 16) | (minor << 8) | patch


def parse_info(d):
    """INFO reply payload (after the status byte) -> dict, same keys as fwupdate.py."""
    if len(d) < 59:
        raise FwError('INFO reply too short (%d bytes)' % len(d))
    proto, running, confirmed, pending, attempts, max_att, _ = struct.unpack_from('<7B', d, 0)
    slots = []
    for s in range(2):
        valid, ver, crc, size, built = struct.unpack_from('<B3xIIII', d, 7 + s * 20)
        slots.append(dict(valid=bool(valid), version=ver, crc=crc, size=size, built=built))
    slot_a, slot_b, slot_size = struct.unpack_from('<III', d, 47)
    return dict(proto=proto, running=running, confirmed=confirmed, pending=pending,
                attempts=attempts, max_attempts=max_att, slots=slots,
                slot_base=(slot_a, slot_b), slot_size=slot_size)


def info_state(i):
    """One word for the boot state (see rover_interfaces/msg/FirmwareInfo.msg)."""
    if i['running'] == SLOT_NONE:
        return 'recovery'
    if i['pending'] != SLOT_NONE:
        return 'rejected' if i['attempts'] >= i['max_attempts'] else 'trial'
    if i['confirmed'] != i['running']:
        return 'unconfirmed'
    return 'ok'


# --- images -------------------------------------------------------------------
def load_image(source, slot, slot_base, slot_size):
    """rover_app_<slot>.bin from a build folder or a package .tar.gz -> (bytes, version).
    Checked against the board's layout, so an image for another board is refused."""
    name = 'rover_app_%s.bin' % 'AB'[slot]
    source = os.path.expanduser(source)
    if os.path.isdir(source):
        path = os.path.join(source, name)
        if not os.path.exists(path):
            raise FwError('%s not found in %s' % (name, source))
        with open(path, 'rb') as f:
            data = f.read()
    elif os.path.isfile(source) and tarfile.is_tarfile(source):
        with tarfile.open(source) as tar:
            member = next((m for m in tar.getmembers()
                           if m.isfile() and os.path.basename(m.name) == name), None)
            if member is None:
                raise FwError('%s not found in %s' % (name, source))
            data = tar.extractfile(member).read()
    else:
        raise FwError('%s: give a build folder (out/<board>/<config>) or a package .tar.gz' % source)

    if len(data) < IMAGE_HEADER_SIZE:
        raise FwError('%s is too small to hold an image header' % name)
    fields = struct.unpack_from(HEADER_FMT, data, 0)
    magic, _, load_addr, size, crc, version = fields[:6]
    if magic != IMAGE_MAGIC:
        raise FwError('%s has no valid image header' % name)
    if load_addr != slot_base:
        raise FwError('%s is linked for 0x%08X, but slot %s on this board is at 0x%08X - '
                      'built for another board?' % (name, load_addr, 'AB'[slot], slot_base))
    if len(data) > slot_size:
        raise FwError('%s (%d bytes) does not fit in a %d byte slot' % (name, len(data), slot_size))
    if zlib.crc32(data[IMAGE_HEADER_SIZE:IMAGE_HEADER_SIZE + size]) != crc:
        raise FwError('%s is corrupt (CRC mismatch)' % name)
    return data, version
