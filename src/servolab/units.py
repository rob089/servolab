"""
units.py - turning raw register numbers into meaningful numbers (and back).

The motor only knows integers: "position 3072", "current 154", "voltage 74".
servolab always gives you SI units instead: rad, rad/s, A, V, degrees Celsius.
Every conversion formula lives in this one file, so you can look them all up here.

Raw format in short:
- Position: 4096 steps per revolution. Step 2048 is the middle -> we call it 0 rad.
- Velocity: steps per second.
- Current:  1 step = 6.5 mA.
- Voltage:  1 step = 0.1 V.
- Load and PWM: 1000 = 100 %.
- IMU: acceleration in mg (1/1000 g), angular velocity in mrad/s,
  orientation as a quaternion made of "half floats" (see the end of this file).
"""

import math
import struct

STEPS_PER_REVOLUTION = 4096
CENTER_STEPS = 2048          # this raw position is 0 rad in servolab

CURRENT_AMPS_PER_STEP = 0.0065   # 6.5 mA (Feetech memory table: at most 500 steps = 3.25 A)
VOLTS_PER_STEP = 0.1
# 1 unit of the acceleration register = 100 steps/s^2 (Feetech data sheet;
# measured on an STS3215 with firmware 3.10: 104 ... 105 steps/s^2)
ACCELERATION_STEPS_PER_UNIT = 100


# ---------------------------------------------------------------------------
# Bytes <-> integers
# ---------------------------------------------------------------------------
# A register can be 1 or 2 bytes long. A byte holds 0...255.
# Two-byte values are sent "low byte first" (little endian):
#     value = low_byte + 256 * high_byte

def bytes_to_int(data):
    """[low, high] -> integer.  Example: [0, 8] -> 0 + 8*256 = 2048"""
    value = 0
    for position, byte in enumerate(data):
        value += byte * 256 ** position
    return value


def int_to_bytes(value, size):
    """Integer -> list of `size` bytes, low byte first.  Example: (2048, 2) -> [0, 8]"""
    data = []
    for _ in range(size):
        data.append(value % 256)
        value = value // 256
    return data


# ---------------------------------------------------------------------------
# Negative numbers: "sign-magnitude"
# ---------------------------------------------------------------------------
# Feetech stores negative numbers in an unusual way: one bit (the "sign bit")
# says "this number is negative", the other bits hold the size of the number.
#
# Example with sign bit 15 (that is the value 32768):
#     +100 is stored as 100
#     -100 is stored as 100 + 32768 = 32868
#
# Which bit is the sign bit depends on the register (see registers.py).

def decode_sign_magnitude(raw, sign_bit):
    """Raw register value -> signed integer.  Example: (32868, 15) -> -100"""
    sign_value = 2 ** sign_bit
    if raw >= sign_value:              # sign bit is set -> negative number
        return -(raw - sign_value)
    return raw


def encode_sign_magnitude(value, sign_bit):
    """Signed integer -> raw register value.  Example: (-100, 15) -> 32868"""
    sign_value = 2 ** sign_bit
    if value < 0:
        return -value + sign_value
    return value


# ---------------------------------------------------------------------------
# Position and velocity
# ---------------------------------------------------------------------------

def steps_to_rad(steps):
    """Raw position -> rad.  2048 -> 0.0,  3072 -> +pi/2,  1024 -> -pi/2"""
    return (steps - CENTER_STEPS) * 2 * math.pi / STEPS_PER_REVOLUTION


def rad_to_steps(rad):
    """rad -> raw position.  0.0 -> 2048,  +pi/2 -> 3072"""
    return round(rad * STEPS_PER_REVOLUTION / (2 * math.pi)) + CENTER_STEPS


def steps_per_s_to_rad_per_s(steps_per_s):
    """Raw velocity (steps/s) -> rad/s.  4096 steps/s = one turn per second = 2*pi rad/s"""
    return steps_per_s * 2 * math.pi / STEPS_PER_REVOLUTION


def rad_per_s_to_steps_per_s(rad_per_s):
    """rad/s -> raw velocity (steps/s)."""
    return round(rad_per_s * STEPS_PER_REVOLUTION / (2 * math.pi))


def acceleration_to_raw(rad_per_s2):
    """rad/s^2 -> value for the acceleration register (0...254, 0 = as fast as possible)."""
    steps_per_s2 = abs(rad_per_s2) * STEPS_PER_REVOLUTION / (2 * math.pi)
    raw = round(steps_per_s2 / ACCELERATION_STEPS_PER_UNIT)
    return min(max(raw, 1), 254)


# ---------------------------------------------------------------------------
# Electrical values and percentages
# ---------------------------------------------------------------------------

def raw_to_amps(raw):
    """Raw current -> A."""
    return raw * CURRENT_AMPS_PER_STEP


def raw_to_volts(raw):
    """Raw voltage -> V.  74 -> 7.4 V"""
    return raw * VOLTS_PER_STEP


def raw_to_fraction(raw):
    """Raw per-mille value (load, PWM) -> fraction.  1000 -> 1.0,  -500 -> -0.5"""
    return raw / 1000


def fraction_to_raw(fraction):
    """Fraction -1.0 ... +1.0 -> raw per-mille value -1000 ... +1000 (clipped)."""
    fraction = min(max(fraction, -1.0), 1.0)
    return round(fraction * 1000)


# ---------------------------------------------------------------------------
# PWM
# ---------------------------------------------------------------------------
# In PWM mode the motor reads its PWM from the goal_time register:
# -1000 ... +1000, with the sign in bit 10.
#
# Measured on the STS3215: a POSITIVE raw PWM turns the motor towards
# SMALLER angles. servolab flips the sign, so that m.pwm > 0 turns towards
# larger angles - the same direction as m.velocity > 0.
PWM_DIRECTION = -1


def pwm_to_raw(fraction):
    """PWM -1.0 ... 1.0 -> raw goal_time value.  0.5 -> -500 -> 500 + 1024 = 1524"""
    raw = fraction_to_raw(fraction) * PWM_DIRECTION
    return encode_sign_magnitude(raw, 10)


def raw_to_pwm(raw):
    """Raw goal_time value -> PWM -1.0 ... 1.0 (reverse of pwm_to_raw)."""
    value = decode_sign_magnitude(raw, 10) * PWM_DIRECTION
    return raw_to_fraction(value)


# ---------------------------------------------------------------------------
# IMU
# ---------------------------------------------------------------------------
# The IMU sends acceleration in mg (1/1000 of gravity) and angular velocity in
# mrad/s (1/1000 rad/s), both sign-magnitude with sign bit 15 like the motors.
#
# Its orientation is a quaternion (w, x, y, z): four numbers that describe a
# rotation without the problems of angles (no gimbal lock). Only x, y and z are
# sent, as "half floats": floating point numbers packed into 16 bits (2 bytes),
# exact to about 3 decimal places. w follows from them, because the four
# numbers of a rotation always satisfy w^2 + x^2 + y^2 + z^2 = 1.

GRAVITY = 9.80665              # m/s^2, one g


def mg_to_m_per_s2(raw):
    """Acceleration in mg -> m/s^2.  1000 -> 9.81"""
    return raw / 1000 * GRAVITY


def mrad_per_s_to_rad_per_s(raw):
    """Angular velocity in mrad/s -> rad/s.  1000 -> 1.0"""
    return raw / 1000


def half_float_to_float(raw):
    """16-bit half float (as an integer) -> Python float.  15360 (= 0x3C00) -> 1.0"""
    # struct does the work: "<e" means "a half float, low byte first".
    return struct.unpack("<e", bytes(int_to_bytes(raw, 2)))[0]


def quaternion_from_xyz(x, y, z):
    """x, y, z of a rotation quaternion -> [w, x, y, z], with w >= 0."""
    w = math.sqrt(max(0.0, 1.0 - x * x - y * y - z * z))
    return [w, x, y, z]
