import math

from servolab import units


def test_bytes_roundtrip():
    assert units.bytes_to_int([0, 8]) == 2048
    assert units.int_to_bytes(2048, 2) == [0, 8]
    assert units.int_to_bytes(7, 1) == [7]


def test_sign_magnitude():
    assert units.decode_sign_magnitude(32868, 15) == -100
    assert units.encode_sign_magnitude(-100, 15) == 32868
    assert units.encode_sign_magnitude(100, 15) == 100
    for value in (-2047, -1, 0, 1, 2047):
        assert units.decode_sign_magnitude(units.encode_sign_magnitude(value, 11), 11) == value


def test_position():
    assert units.steps_to_rad(2048) == 0.0
    assert math.isclose(units.steps_to_rad(3072), math.pi / 2)
    assert units.rad_to_steps(0.0) == 2048
    assert units.rad_to_steps(-math.pi / 2) == 1024


def test_fraction_is_clipped():
    assert units.fraction_to_raw(2.0) == 1000
    assert units.fraction_to_raw(-0.5) == -500


def test_pwm_direction_and_encoding():
    # positive servolab PWM -> negative raw PWM (sign bit 10 set)
    assert units.pwm_to_raw(0.5) == 500 + 1024
    assert units.pwm_to_raw(-0.5) == 500
    assert units.raw_to_pwm(units.pwm_to_raw(0.25)) == 0.25
