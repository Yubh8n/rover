import struct
import zlib

import pytest

from rover_stm32 import protocol as p


@pytest.mark.parametrize('data', [b'', b'\0', b'\0\0', b'abc', b'a\0b', bytes(range(256)) * 3,
                                  b'\x01' * 254, b'\x01' * 255, b'\x01' * 253 + b'\0'])
def test_cobs_roundtrip(data):
    enc = p.cobs_encode(data)
    assert b'\0' not in enc
    assert p.cobs_decode(enc) == data


def test_frame_roundtrip_with_noise():
    parser = p.FrameParser()
    f1 = p.encode_frame(0x41, 7, b'\x00\x01\x02')
    f2 = p.encode_frame(0x81, 9, bytes([0]) + b'x' * 60)
    stream = b'debug text\r\n' + f1 + b'\xff\xfe' + f2
    frames = []
    for i in range(0, len(stream), 5):          # arrives in small pieces
        frames += parser.feed(stream[i:i + 5])
    assert frames == [(0x41, 7, b'\x00\x01\x02'), (0x81, 9, bytes([0]) + b'x' * 60)]


def test_frame_bad_crc_dropped():
    f = bytearray(p.encode_frame(0x41, 1, b'hello'))
    raw = p.cobs_decode(bytes(f[1:-1]))
    bad = raw[:-1] + bytes([raw[-1] ^ 1])
    assert p.FrameParser().feed(b'\0' + p.cobs_encode(bad) + b'\0') == []


def test_encode_matches_wire_format():
    body = bytes([0x01, 0x05])
    expected = b'\0' + p.cobs_encode(body + struct.pack('<I', zlib.crc32(body))) + b'\0'
    assert p.encode_frame(p.CMD_INFO, 5) == expected


def make_info(running=0, confirmed=0, pending=0xFF, attempts=0):
    d = bytearray(59)
    d[0:7] = bytes([1, running, confirmed, pending, attempts, 3, 0])
    struct.pack_into('<B3xIIII', d, 7, 1, p.parse_version('0.2.1'), 0xDEADBEEF, 4096, 1700000000)
    struct.pack_into('<III', d, 47, 0x08004000, 0x08011800, 0xD800)
    return bytes(d)


def test_parse_info():
    i = p.parse_info(make_info())
    assert i['running'] == 0 and i['pending'] == p.SLOT_NONE
    assert i['slots'][0]['valid'] and p.fmt_version(i['slots'][0]['version']) == '0.2.1'
    assert not i['slots'][1]['valid']
    assert i['slot_base'] == (0x08004000, 0x08011800) and i['slot_size'] == 0xD800


@pytest.mark.parametrize('kw,state', [
    (dict(), 'ok'),
    (dict(running=0xFF, confirmed=0xFF), 'recovery'),
    (dict(running=1, confirmed=0, pending=1, attempts=1), 'trial'),
    (dict(running=0, confirmed=0, pending=1, attempts=3), 'rejected'),
    (dict(running=1, confirmed=0), 'unconfirmed'),
])
def test_info_state(kw, state):
    assert p.info_state(p.parse_info(make_info(**kw))) == state


def make_image(tmp_path, slot, base, version='1.2.3', body=b'\x11' * 1024):
    hdr = struct.pack(p.HEADER_FMT, p.IMAGE_MAGIC, 1, base, len(body), zlib.crc32(body),
                      p.parse_version(version), 0, *([0] * 8), b'rover-app', 0)
    data = hdr + bytes(p.IMAGE_HEADER_SIZE - len(hdr)) + body
    (tmp_path / ('rover_app_%s.bin' % 'AB'[slot])).write_bytes(data)
    return data


def test_load_image(tmp_path):
    data = make_image(tmp_path, 1, 0x08011800)
    got, ver = p.load_image(str(tmp_path), 1, 0x08011800, 0xD800)
    assert got == data and p.fmt_version(ver) == '1.2.3'
    with pytest.raises(p.FwError, match='another board'):
        p.load_image(str(tmp_path), 1, 0x08080000, 0xD800)
    with pytest.raises(p.FwError, match='not found'):
        p.load_image(str(tmp_path), 0, 0x08004000, 0xD800)
