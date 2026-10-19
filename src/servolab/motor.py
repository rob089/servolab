"""
motor.py - one motor, with all values in SI units.

You never create a Motor yourself. You get it from the bus:

    bus = servolab.connect()
    m = bus[1]                   # the motor with ID 1 (an ID, not a list index)

    m.position                   # where is it? (rad)
    m.mode = "position"
    m.torque_enabled = True
    m.position = 0.5             # go to 0.5 rad

Reading a value always asks the motor right now (one message on the bus).
Writing a value sends it to the motor right away.

About "@property": it lets a function look like a variable. When you write
m.position, Python calls the function below that is marked with @property.
When you write m.position = 0.5, Python calls the function marked with
@position.setter. That's all there is to it.
"""

import time

from servolab import units
from servolab.errors import RegisterError, ServoLabError, decode_status
from servolab.registers import REGISTER_TABLES

# Operating modes: name used in servolab -> number in the operating_mode register
MODES = {
    "position": 0,   # motor goes to a goal position and holds it
    "velocity": 1,   # motor turns at a goal speed
    "pwm": 2,        # you set the motor voltage directly (no controller in the motor)
}


class Motor:
    """One Feetech motor on the bus."""

    # Only these attributes exist. A typo like  m.postion = 1  then gives an
    # error, instead of silently creating a new variable that does nothing.
    __slots__ = ("bus", "_id", "model", "_mode", "_zero_correction")

    def __init__(self, bus, motor_id, model):
        self.bus = bus
        self._id = motor_id    # use m.id (see below)
        self.model = model     # e.g. "STS3215"
        self._mode = None
        self._zero_correction = 0   # steps to subtract from present_position, see present_steps()

    def __repr__(self):
        return f"<Motor {self.id}: {self.model}>"

    @property
    def id(self):
        """ID of the motor on the bus.

        Writing m.id = 2 gives the motor a new ID (saved permanently in the
        motor). No other motor on the bus may already have this ID.
        """
        return self._id

    @id.setter
    def id(self, new_id):
        self.bus.change_id(self._id, new_id)

    # =======================================================================
    # Reading values
    # =======================================================================

    @property
    def position(self):
        """Present position in rad. 0 = middle (or the zero of set_zero()), range -pi ... +pi.

        The same angle in every mode. Writing m.position = x sets the goal
        position (only in position mode).
        """
        raw = self.read_register("present_position")
        return units.steps_to_rad(self.present_steps(raw))

    @position.setter
    def position(self, rad):
        self.require_mode("position")
        self.write_register("goal_position", units.rad_to_steps(rad))

    @property
    def velocity(self):
        """Present velocity in rad/s.

        Writing m.velocity = x sets the goal velocity (only in velocity mode).
        """
        raw = self.read_register("present_velocity")
        return units.steps_per_s_to_rad_per_s(raw)

    @velocity.setter
    def velocity(self, rad_per_s):
        self.require_mode("velocity")
        self.write_register("goal_velocity", units.rad_per_s_to_steps_per_s(rad_per_s))

    @property
    def pwm(self):
        """PWM output, -1.0 ... 1.0 (1.0 = full voltage). Only in pwm mode.

        PWM means: the motor gets this fraction of the supply voltage.
        There is no controller in between - that's your job.
        """
        return units.raw_to_pwm(self.read_register("goal_time"))

    @pwm.setter
    def pwm(self, fraction):
        self.require_mode("pwm")
        self.write_register("goal_time", units.pwm_to_raw(fraction))

    @property
    def current(self):
        """Motor current in A."""
        return units.raw_to_amps(self.read_register("present_current"))

    @property
    def load(self):
        """How hard the motor works, -1.0 ... 1.0 (1.0 = 100 %)."""
        return units.raw_to_fraction(self.read_register("present_load"))

    @property
    def voltage(self):
        """Supply voltage in V."""
        return units.raw_to_volts(self.read_register("present_voltage"))

    @property
    def temperature(self):
        """Temperature inside the motor in degrees Celsius."""
        return self.read_register("present_temperature")

    @property
    def moving(self):
        """True while the motor is moving."""
        return self.read_register("moving") == 1

    @property
    def status(self):
        """List of active problems, e.g. ['overheat']. Empty list = all fine."""
        return decode_status(self.read_register("status"))

    # =======================================================================
    # Settings
    # =======================================================================

    @property
    def torque_enabled(self):
        """True = motor is powered and holds/moves. False = motor is free."""
        return self.read_register("torque_enable") == 1

    @torque_enabled.setter
    def torque_enabled(self, enabled):
        if enabled and self._mode == "position":
            # Safety: hold the current position instead of jumping to an old goal.
            self.write_register("goal_position", self.read_register("present_position"))
        self.write_register("torque_enable", 1 if enabled else 0)

    @property
    def mode(self):
        """Operating mode: "position", "velocity" or "pwm"."""
        return self._mode

    @mode.setter
    def mode(self, new_mode):
        if new_mode not in MODES:
            raise ServoLabError(f"Unknown mode '{new_mode}'. Choose one of {list(MODES)}.")

        # Safety first: make sure the motor does not jump or spin off
        # as soon as the new mode is active.
        if new_mode == "position":
            # stay where you are, and forget a PWM value left in goal_time
            # (in position mode, goal_time != 0 would override the speed).
            # present_steps(): coming from pwm mode, the motor still reports the bare encoder.
            here = self.present_steps(self.read_register("present_position"))
            self.write_register("goal_position", here)
            self.write_register("goal_time", 0)
        if new_mode == "velocity":
            self.write_register("goal_velocity", 0)   # start standing still
        if new_mode == "pwm":
            self.write_register("goal_time", 0)       # start with 0 % PWM

        # (operating_mode is an EEPROM register. With lock = 1, which is the
        # default, the change is active right away but not kept after power-off.)
        self.write_register("operating_mode", MODES[new_mode])

    def update_mode(self):
        """Ask the motor which mode it is in and remember it (normally you just use m.mode)."""
        number = self.read_register("operating_mode")
        self._mode = f"unknown ({number})"
        for name, mode_number in MODES.items():
            if mode_number == number:
                self._mode = name

        # The motor subtracts homing_offset (the zero of set_zero()) from
        # present_position only in position mode. In the other modes it
        # reports the bare encoder, so present_steps() subtracts it instead.
        if self._mode == "position":
            self._zero_correction = 0
        else:
            self._zero_correction = self.read_register("homing_offset")

    def present_steps(self, raw):
        """present_position as the motor sends it -> steps from the zero of set_zero(), in every mode."""
        return (raw - self._zero_correction) % units.STEPS_PER_REVOLUTION

    @property
    def pid(self):
        """Gains (P, I, D) of the controller inside the motor (position mode)."""
        return (
            self.read_register("p_coefficient"),
            self.read_register("i_coefficient"),
            self.read_register("d_coefficient"),
        )

    @pid.setter
    def pid(self, gains):
        p, i, d = gains
        self.write_register("p_coefficient", p)
        self.write_register("i_coefficient", i)
        self.write_register("d_coefficient", d)

    @property
    def info(self):
        """Overview of the motor, as a dict."""
        return {
            "id": self.id,
            "model": self.model,
            "firmware": f"{self.read_register('firmware_major')}.{self.read_register('firmware_minor')}",
            "mode": self.mode,
            "torque_enabled": self.torque_enabled,
            "voltage": self.voltage,
            "temperature": self.temperature,
            "status": self.status,
        }

    # =======================================================================
    # Actions
    # =======================================================================

    def move_to(self, rad, speed=None, acceleration=None, wait=False, timeout=10.0):
        """Go to a position, optionally with speed and acceleration limits.

        rad:          goal position in rad
        speed:        maximum speed in rad/s (None = as fast as possible)
        acceleration: in rad/s^2 (None = as fast as possible)
        wait:         True = only return when the motor has arrived
        timeout:      give up waiting after this many seconds

        Example:  m.move_to(1.0, speed=2.0, wait=True)
        """
        self.bus.move_to({self.id: rad}, speed=speed, acceleration=acceleration, wait=wait, timeout=timeout)

    def wait_until_arrived(self, rad, timeout=10.0, tolerance=0.02):
        """Wait until the motor is within `tolerance` rad of `rad` and stands still."""
        start = time.perf_counter()
        while not (abs(self.position - rad) < tolerance and not self.moving):
            if time.perf_counter() - start > timeout:
                raise ServoLabError(f"Motor {self.id} did not reach {rad:.2f} rad in {timeout:.1f} s "
                                    f"(it is at {self.position:.2f} rad).")
            time.sleep(0.01)

    def set_zero(self):
        """Make the current position the new 0 rad. Saved permanently in the motor.

        Torque is switched off for this, so the motor does not jump.
        """
        self.torque_enabled = False
        self.write_register("homing_offset", 0)
        raw = self.read_register("present_position")
        offset = raw - units.CENTER_STEPS
        offset = max(-2047, min(2047, offset))
        self.write_register("homing_offset", offset, save=True)

    def factory_reset(self, keep_zero=True):
        """Put all settings back to how the motor came from the factory. Saved permanently.

        Limits, gains, mode, protection ... all go back to the stock values.
        The motor keeps its ID and (unless keep_zero=False) its zero position.
        Afterwards the motor is in position mode (the factory mode).
        """
        self.bus.factory_reset(self.id, keep_zero=keep_zero)
        self.update_mode()

    # =======================================================================
    # Direct register access (for everything the properties above don't cover)
    # =======================================================================

    def read_register(self, name):
        """Read any register by name (see registers.py). Returns the raw value."""
        return self.bus.read_register(self.id, name)

    def write_register(self, name, value, save=False):
        """Write any register by name (see registers.py). `value` is raw.

        save=True keeps an EEPROM value after power-off. Don't do that in
        loops: EEPROM wears out after many writes.
        """
        if name == "id":
            self.id = value     # changing the ID needs special care, see bus.change_id()
            return
        self.bus.write_register(self.id, name, value, save=save)
        if name in ("operating_mode", "homing_offset"):
            self.update_mode()

    def save_to_eeprom(self):
        """Keep all current settings (mode, limits, gains ...) after power-off."""
        for register in REGISTER_TABLES[self.model]:
            if register.memory == "eeprom" and register.access == "rw":
                value = self.read_register(register.name)
                self.write_register(register.name, value, save=True)

    def require_mode(self, mode):
        """Raise a helpful error if the motor is not in the given mode."""
        if self._mode != mode:
            raise RegisterError(f"Motor {self.id} is in {self._mode} mode. Switch first: "
                                f"bus[{self.id}].mode = '{mode}'")

