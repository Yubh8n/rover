# One application slot on the STM32 (from the INFO reply, fw_common/fwproto.c)
string name                     # "A" or "B"
bool valid                      # header (and, for the slot not running, CRC) ok
string version                  # "major.minor.patch", "" if not valid
uint32 version_raw              # (major << 16) | (minor << 8) | patch
uint32 crc                      # CRC-32 of the image
uint32 size                     # image bytes after the 512-byte header
builtin_interfaces/Time built   # build time from the image header
