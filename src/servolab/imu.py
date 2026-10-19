"""
imu.py - an IMU (gyro + accelerometer) on the bus, with all values in SI units.

You never create an Imu yourself. You get it from the bus, like a motor:

    bus = servolab.connect()
    bus.sensors                  # {100: <Imu 100: XIAO IMU>}
    imu = bus[100]               # the IMU with ID 100

    imu.acceleration             # [ax, ay, az] in m/s^2
    imu.angular_velocity         # [wx, wy, wz] in rad/s
    imu.quaternion               # orientation [w, x, y, z]

    fb = imu.read()              # all three from the SAME moment, one message
    fb.acceleration, fb.angular_velocity, fb.quaternion

What the IMU measures:
- angular velocity: how fast it turns around its x, y and z axis (gyro).
- acceleration: the accelerometer feels gravity too. Lying still, it shows
  about 9.81 m/s^2 pointing UP (the force that holds it against gravity).
  Moving, it shows gravity plus its own acceleration.
- orientation: the IMU combines both into a rotation (quaternion) from its
  own axes into a world frame with z up. Without a compass, the heading
  (rotation around z) starts at 0 and drifts slowly.

The axes are printed on the IMU board (or see its README).
"""

from dataclasses import dataclass

import numpy as np

from servolab import units
from servolab.errors import RegisterError
from servolab.registers import REGISTER_TABLES

# The measurements are one block of registers: from quaternion_x (address 56)
# up to acceleration_z (address 77 + 78) = 23 bytes. It starts at the same
# address as the motors' state, so bus.read_feedback() can read both at once.
MEASUREMENTS_START = 56
MEASUREMENTS_SIZE = 23

# Settings: the register holds a number 0, 1, 2 ... that picks one of these.
GYRO_RANGES = [250, 500, 1000, 2000]          # deg/s
ACC_RANGES = [2, 4, 8, 16]                    # g
SAMPLE_RATES = [26, 52, 104, 208, 416, 833]   # Hz


@dataclass
class ImuFeedback:
    """All measurements of one IMU, from the same moment."""

    time: float                    # seconds since connect()
    acceleration: np.ndarray       # [x, y, z] in m/s^2
    angular_velocity: np.ndarray   # [x, y, z] in rad/s
    quaternion: np.ndarray         # [w, x, y, z]


class Imu:
    """One IMU on the bus."""

    # Only these attributes exist (a typo gives an error, see motor.py).
    __slots__ = ("bus", "_id", "model")

    def __init__(self, bus, imu_id, model):
        self.bus = bus
        self._id = imu_id      # use imu.id (see below)
        self.model = model     # e.g. "XIAO IMU"

    def __repr__(self):
        return f"<Imu {self.id}: {self.model}>"

    @property
    def id(self):
        """ID of the IMU on the bus.

        Writing imu.id = 101 gives the IMU a new ID (saved permanently).
        No other device on the bus may already have this ID.
        """
        return self._id

    @id.setter
    def id(self, new_id):
        self.bus.change_id(self._id, new_id)

    # =======================================================================
    # Measurements
    # =======================================================================

    def read(self):
        """Read all measurements with ONE message. Returns an ImuFeedback.

        Use this in loops: acceleration, angular velocity and orientation then
        belong to the same moment.
        """
        block = self.bus.read_bytes(self.id, MEASUREMENTS_START, MEASUREMENTS_SIZE)
        return feedback_from_block(self.bus, self.model, block)

    @property
    def acceleration(self):
        """Acceleration [x, y, z] in m/s^2 (includes gravity, see the top of this file)."""
        return self.read().acceleration

    @property
    def angular_velocity(self):
        """Angular velocity [x, y, z] in rad/s (from the gyro)."""
        return self.read().angular_velocity

    @property
    def quaternion(self):
        """Orientation as a quaternion [w, x, y, z], from the IMU's own filter."""
        return self.read().quaternion

    # =======================================================================
    # Settings
    # =======================================================================
    # Like the motor's mode: active right away, but lost after power-off,
    # unless you call save_to_eeprom().

    @property
    def gyro_range(self):
        """Largest angular velocity the gyro can measure, in deg/s: 250, 500, 1000 or 2000."""
        return GYRO_RANGES[self.read_register("gyro_range")]

    @gyro_range.setter
    def gyro_range(self, deg_per_s):
        self.write_register("gyro_range", index_of_choice("gyro_range", deg_per_s, GYRO_RANGES, "deg/s"))

    @property
    def acc_range(self):
        """Largest acceleration the accelerometer can measure, in g: 2, 4, 8 or 16."""
        return ACC_RANGES[self.read_register("acc_range")]

    @acc_range.setter
    def acc_range(self, g):
        self.write_register("acc_range", index_of_choice("acc_range", g, ACC_RANGES, "g"))

    @property
    def sample_rate(self):
        """Measurements per second, in Hz: 26, 52, 104, 208, 416 or 833."""
        return SAMPLE_RATES[self.read_register("sample_rate")]

    @sample_rate.setter
    def sample_rate(self, hz):
        self.write_register("sample_rate", index_of_choice("sample_rate", hz, SAMPLE_RATES, "Hz"))

    @property
    def info(self):
        """Overview of the IMU, as a dict."""
        return {
            "id": self.id,
            "model": self.model,
            "firmware": f"{self.read_register('firmware_major')}.{self.read_register('firmware_minor')}",
            "gyro_range": self.gyro_range,
            "acc_range": self.acc_range,
            "sample_rate": self.sample_rate,
        }

    # =======================================================================
    # Direct register access (as for motors)
    # =======================================================================

    def read_register(self, name):
        """Read any register by name (see registers.py). Returns the raw value."""
        return self.bus.read_register(self.id, name)

    def write_register(self, name, value, save=False):
        """Write any register by name (see registers.py). `value` is raw.

        save=True keeps an EEPROM value after power-off.
        """
        if name == "id":
            self.id = value     # changing the ID needs special care, see bus.change_id()
            return
        self.bus.write_register(self.id, name, value, save=save)

    def factory_reset(self):
        """Put all settings (ranges, sample rate ...) back to the factory values.

        Saved permanently. The IMU keeps its ID.
        """
        self.bus.factory_reset(self.id)

    def save_to_eeprom(self):
        """Keep all current settings (ranges, sample rate ...) after power-off."""
        for register in REGISTER_TABLES[self.model]:
            if register.memory == "eeprom" and register.access == "rw":
                value = self.read_register(register.name)
                self.write_register(register.name, value, save=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def feedback_from_block(bus, model, block):
    """Turn the measurement bytes (from address 56) into an ImuFeedback.

    Used by imu.read() and by bus.read_feedback().
    """
    def value(name):
        return bus.value_in_block(model, block, name)

    acceleration = [units.mg_to_m_per_s2(value(f"acceleration_{axis}")) for axis in "xyz"]
    angular_velocity = [units.mrad_per_s_to_rad_per_s(value(f"angular_velocity_{axis}")) for axis in "xyz"]
    x, y, z = [units.half_float_to_float(value(f"quaternion_{axis}")) for axis in "xyz"]
    return ImuFeedback(
        time=bus.elapsed_time(),
        acceleration=np.array(acceleration),
        angular_velocity=np.array(angular_velocity),
        quaternion=np.array(units.quaternion_from_xyz(x, y, z)),
    )


def index_of_choice(name, value, choices, unit):
    """Which of the allowed choices is `value`? Raises a helpful error if none."""
    if value not in choices:
        allowed = ", ".join(str(choice) for choice in choices)
        raise RegisterError(f"{name} can be {allowed} {unit}, not {value}.")
    return choices.index(value)
