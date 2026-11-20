# Firmware / boot state of the STM32, from the INFO command (fw_common/fwproto.h)
builtin_interfaces/Time stamp
bool connected                  # INFO answered on the last poll
string port                     # serial port in use

# state: "ok"           running a confirmed image
#        "unconfirmed"  running an image that has not confirmed itself yet
#        "trial"        an update is pending and being tried
#        "rejected"     the last update never confirmed - the bootloader rolled back
#        "recovery"     only the bootloader runs (no valid app)
#        "disconnected" no answer from the STM32
string state

uint8 protocol_version
string running                  # "A", "B" or "bootloader"
string running_version          # version of the running image, "" if unknown
string confirmed                # "A", "B" or "-"
string pending                  # "A", "B" or "-"
uint8 attempts                  # trial boots done for the pending image
uint8 max_attempts              # rollback after this many

FirmwareSlot[] slots            # [A, B]
uint32 slot_a_addr
uint32 slot_b_addr
uint32 slot_size

string error                    # last error, "" if none
