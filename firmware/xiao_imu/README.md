# Feetech bus IMU (XIAO nRF52840 Sense)

Firmware that turns a Seeed XIAO nRF52840 Sense into an IMU node on the Feetech
STS servo bus. It answers the Feetech protocol like a servo, with its own ID,
and copies the register layout of Feetech's own (unreleased) bus IMU from
their Python SDK (`scservo_sdk/imu.py`). So Feetech's SDK, and later servolab,
can read it on the same bus as the servos.

- gyro + accelerometer: the XIAO's LSM6DS3TR-C, 416 Hz by default
- orientation: Mahony filter on the chip, sent as a quaternion
- the USB port speaks the same protocol: testing needs no bus hardware

## Build and flash

```
pio run -t upload
```

PlatformIO platform: Max Gerhardt's fork of `nordicnrf52` (the official one has
no XIAO), board `xiaoblesense_adafruit`, uploads over USB (double-tap reset if
the upload does not find the board). `platformio.ini` pins GCC 12 because the
platform's default GCC 7 is an Intel-only binary.

## Test 1: USB only (no wiring)

The XIAO's USB port behaves like a bus adapter with only the IMU on it.

```
python tools/imu_tool.py /dev/cu.usbmodemXXXX            # live values
python tools/imu_tool.py /dev/cu.usbmodemXXXX --check    # protocol self-test
python tools/imu_tool.py /dev/cu.usbmodemXXXX --set-id 101
```

Run it with the servolab environment (the tool uses Feetech's SDK bundled in
`servolab._sdk`). `--check` expects the board to lie still.

## Test 2: on the servo bus, without the PCB ("resistor hack")

With the Waveshare Bus Servo Adapter (A) (bus DATA is pulled up to 3.3 V):

```
 XIAO               servo bus (adapter / servo connector)
 GND  ------------- GND
 D7 (RX) ---------- DATA
 D6 (TX) --[1k]---- DATA
                    V+ (7.4 V): NOT connected, the XIAO is powered over USB
```

The XIAO's TX pin always drives (idle = high). The 1 kOhm resistor keeps that
harmless when an adapter or servo pulls DATA low (about 3 mA), and is still
strong enough to drive the bus at 1 Mbaud. D8 is not needed here. Measure the
high level on DATA once while servos answer: it must not exceed 3.3 V (the
nRF52840 pins are not 5 V tolerant).

Then `python tools/imu_tool.py <adapter port> --check` (default ID 100).

## The PCB

The firmware is for PCB v2. PCB v1 has two errors:

- The D0-D6 header row is mirrored (the 5V/GND/3V3/D10-D7 row is correct), so
  the TX trace lands on D0 instead of the XIAO's default D6. Set `PIN_BUS_TX`
  in `src/config.h` to `D0` for a v1 board.
- Buffer 2 is reversed: 2A is on UART_RX and 2Y on DATA, so the chip drives the
  bus from the floating RX pin (always, 2OE# is at GND) and nothing reaches D7.
  Keep an unmodified board off a bus with servos. Bodge: lift pin 5 (2A) and
  bridge it to pin 6 (1Y = DATA); lift pin 3 (2Y) and wire it to D7 (or to the
  free pad 5, still on the UART_RX trace).

`pio run -e bus_debug -t upload` builds a debug firmware that prints, over USB,
what arrives on the bus (byte and packet counts, D7 level, whether D7 is driven).
Open it with `pio device monitor -e bus_debug`.

- D6 (TX) -> 74LVC2G125 1A, 1Y -> bus; 1OE# = D8 (LOW = we send).
- Bus -> 2A, 2Y -> D7 (RX); 2OE# to GND (always on, we hear our own echo and
  discard it).
- Put a pull-up (e.g. 10 kOhm to 3.3 V) on 1OE#: D8 floats during reset and
  in the bootloader, and the buffer must not drive the bus then.
- The firmware releases the bus (D8 HIGH) right after the echo of the last
  byte is back.

## Registers

Same addresses as Feetech's IMU, multi-byte values little endian.

| addr | size | access | area | meaning |
|---|---|---|---|---|
| 0, 1 | 1+1 | r | eeprom | firmware version major, minor |
| 3 | 2 | r | eeprom | model number: **2026** (our choice, Feetech publishes none) |
| 5 | 1 | rw | eeprom | ID, default **100** (servos come with 1) |
| 6 | 1 | rw | eeprom | baud rate code, 0 = 1 Mbaud ... 7 = 38400 (as the servos) |
| 11 | 1 | rw | eeprom | gyro range: 0 = 250, 1 = 500, 2 = 1000, **3 = 2000** deg/s |
| 12 | 1 | rw | eeprom | acc range: 0 = 2, 1 = 4, **2 = 8**, 3 = 16 g |
| 13 | 1 | rw | eeprom | sample rate: 0 = 26, 1 = 52, 2 = 104, 3 = 208, **4 = 416**, 5 = 833 Hz |
| 55 | 1 | rw | ram | lock: 1 = EEPROM writes are not kept (default) |
| 56 | 6 | r | ram | quaternion x, y, z, half floats; w = sqrt(1 - x² - y² - z²) |
| 62, 65, 68 | 2 each | r | ram | angular velocity x, y, z in **mrad/s** |
| 71, 74, 77 | 2 each | r | ram | acceleration x, y, z in **mg** |

- Angular velocity and acceleration are sign-magnitude like the servos (bit 15
  = sign): -5 is `0x8005`. Bytes 64, 67, 70, 73, 76 are unused (0), as in
  Feetech's map.
- Units are fixed; the range registers only set the chip's measuring range.
  1 mrad/s (0.057 deg/s) is finer than the chip's step at 2000 deg/s
  (70 mdeg/s), 1 mg finer than its noise. Limits: +-32.7 rad/s, +-32 g.
- EEPROM registers take effect at once, but are only kept over power-off if
  written while lock = 0 (same as the servos: unlock, write, lock).
- Feetech has not documented their units; ours are our own choice.

Instructions: PING, READ, WRITE, REG_WRITE + ACTION, SYNC_READ, SYNC_WRITE,
RESET (factory defaults, keeps the ID). No answers to broadcasts (except
SYNC_READ). In a SYNC_READ on the bus the IMU answers in its turn: after the
device listed before it, or after 1 ms of silence if that one is missing.
The ERROR byte has bit 1 set while the IMU chip does not answer.

## Orientation

- Axes: those of the LSM6DS3TR-C as soldered on the XIAO.
- The quaternion turns sensor coordinates into a world frame with z up.
  There is no magnetometer: yaw starts at 0 and drifts slowly (measured at
  rest: about 0.4 deg/min). Roll and pitch are held by gravity.
- Feetech sends only x, y, z; we keep w >= 0 (q and -q are the same rotation).
- At power-up the gyro offset is measured: the blue LED is on until the board
  has been still for 0.5 s.

## LEDs

| LED | meaning |
|---|---|
| blue | measuring gyro offset, keep still |
| green flash | answered a request |
| red | IMU chip not found (retried every second) |

## Notes for servolab

- Feetech's `imu.readSlfp()` calls `scs_halffloat()`, which does not exist in
  the SDK: decode the half floats yourself (`struct.unpack("<e", ...)`), see
  `tools/imu_tool.py`.
- `bus.scan()` would currently treat the IMU (model 2026) as a motor; it needs
  its own class.
- Reading 56..78 in one READ gives everything (23 bytes); a SYNC_READ from
  address 56 can include servos and the IMU in one packet.

## Files

```
src/main.cpp        setup, loop, LEDs
src/protocol.*      Feetech packets on USB and on the bus
src/registers.*     memory table, flash storage of the EEPROM registers
src/imu.*           LSM6DS3TR-C driver and Mahony filter
src/config.h        pins, defaults, model number
tools/imu_tool.py   live view, self-test, change ID
```
