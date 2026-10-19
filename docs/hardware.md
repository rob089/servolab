# Hardware

## Wiring

```text
computer --USB--> Waveshare Bus Servo Adapter --3-pin cable--> motor --> motor --> ...
                       ^ 7.4 V power supply
```

The USB cable does not power the motors: the adapter needs its own supply
(7.4 V for the STS3215 7.4 V version). All motors hang on one chain ("bus").

## IDs

Every device on the bus needs its own ID. New motors all have ID 1, so connect
them one at a time and give each a new ID first:

```python
bus = servolab.connect()        # only the new motor on the cable
bus[1].id = 2                   # saved permanently in the motor
```

or in ServoScope: Settings → Identity → `id`. Two devices with the same ID
disturb each other: every command reaches both, and their answers collide.
`bus.scan()` notices this and raises a `DuplicateIdError` that names the ID.
A factory reset keeps the ID.

## The bus IMU

`firmware/xiao_imu/` in the repository turns a Seeed XIAO nRF52840 Sense into
an IMU on the servo bus: it answers the Feetech protocol like a servo, with its
own ID (100 when new), so servolab reads it together with the motors (see the
[IMU guide](guides/imu.md)). Build and wiring instructions are in its
[README](https://github.com/rob089/servolab/tree/main/firmware/xiao_imu).

## Checked on hardware

On an STS3215 with firmware 3.10:

- `homing_offset` (the zero of `m.set_zero()`) is applied by the motor only in
  position mode. servolab applies it in velocity and PWM mode, so the zero is
  the same in every mode.
- EEPROM `lock`: with lock = 1 (the default after power-on) EEPROM writes are
  active right away but lost after power-off; `save=True` keeps them.
- Factory reset: the motor resets with instruction 0x06 (the Feetech SDK's
  0x0A is ignored), keeps its ID and clears `homing_offset`.
  `m.factory_reset()` writes the zero back.
- Acceleration register: 104 ... 105 steps/s² per unit (data sheet: 100).
- PWM mode: the PWM value is in `goal_time` (address 44), sign in bit 10. The
  raw PWM direction is opposite to the angle direction; servolab corrects this
  (`units.PWM_DIRECTION`).
- Current: 6.5 mA per step, as in the Feetech memory table (not measured
  separately).
- Two motors with the same ID: about 4 in 10 reads of the state block come
  back garbled or followed by extra bytes; most others look fine but hold the
  values of only one of the motors, and a ping misses the ID 3 to 4 times in
  10. `bus.scan()` therefore checks every ID it finds with 20 reads: it found
  the duplicate in 10 of 10 connects, and gave no false alarm in 20 connects
  with a single motor.
