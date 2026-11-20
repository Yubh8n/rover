# One application frame on the STM32 link.
# cmd 0x40..0x7F are free for Rover messages (fwproto_app_command() on the STM32);
# replies from the STM32 have bit 7 set (cmd | 0x80) and start with a status byte.
uint8 cmd
uint8 seq
uint8[] payload
