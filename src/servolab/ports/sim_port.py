"""
sim_port.py - pretend motors, for working without hardware.

    bus = servolab.connect("sim")

gives you a bus with simulated STS3215 motors. Everything works like with
real motors: the same registers, the same six port methods as feetech_port.py.
Useful at home, for testing, and for developing ServoScope.

Each simulated motor is just
  1. a memory table (a list of 256 bytes, like the real motor's registers), and
  2. a tiny physics model that moves the motor towards its goal over time.

The physics is deliberately simple. It is "plausible", not "accurate":
don't tune real controllers on it.
"""

import time

from servolab import units
from servolab.errors import NoResponseError
from servolab.registers import STS3215_REGISTERS, find_register

MAX_SPEED = 3000           # steps/s, roughly an STS3215 at 7.4 V without load
POSITION_GAIN = 8.0        # 1/s, how strongly position mode pulls towards the goal (at P = 32)
VELOCITY_TIME_CONSTANT = 0.05   # s, how quickly the motor reaches a new speed
FREE_TIME_CONSTANT = 0.3        # s, how quickly a free (torque off) motor coasts to a stop
LONGEST_STEP = 0.005            # s, physics is calculated in steps of at most 5 ms


class SimMotor:
    """One simulated motor."""

    def __init__(self, motor_id):
        self.memory = [0] * 256
        self.position = float(units.CENTER_STEPS)  # true shaft position (encoder), in steps
        self.velocity = 0.0                         # true speed, in steps/s

        # Factory defaults, like a new STS3215
        self.set("model_number", 777)
        self.set("firmware_major", 3)
        self.set("firmware_minor", 10)
        self.set("id", motor_id)
        self.set("max_position_limit", 4095)
        self.set("max_temperature_limit", 70)
        self.set("max_voltage_limit", 140)
        self.set("min_voltage_limit", 40)
        self.set("max_torque_limit", 1000)
        self.set("torque_limit", 1000)
        self.set("p_coefficient", 32)
        self.set("d_coefficient", 32)
        self.set("i_coefficient", 0)
        self.set("lock", 1)
        self.set("goal_position", units.CENTER_STEPS)
        self.set("present_voltage", 74)
        self.set("present_temperature", 30)
        self.update_present_values(target_velocity=0.0)

    def factory_reset(self):
        """Like the reset instruction: all EEPROM settings back to factory values.

        The ID stays, homing_offset becomes 0 (like on a real STS3215).
        """
        factory = SimMotor(self.get("id"))
        for register in STS3215_REGISTERS:
            if register.memory == "eeprom":
                end = register.address + register.size
                self.memory[register.address:end] = factory.memory[register.address:end]

    # -- reading and writing the memory table by register name --------------

    def get(self, name):
        """Value of a register, by name (decoded like bus.read_register())."""
        register = find_register("STS3215", name)
        data = self.memory[register.address:register.address + register.size]
        raw = units.bytes_to_int(data)
        if register.sign_bit is not None:
            return units.decode_sign_magnitude(raw, register.sign_bit)
        return raw

    def set(self, name, value):
        """Store a value in a register, by name (encoded like bus.write_register())."""
        register = find_register("STS3215", name)
        if register.sign_bit is not None:
            value = units.encode_sign_magnitude(value, register.sign_bit)
        data = units.int_to_bytes(value, register.size)
        self.memory[register.address:register.address + register.size] = data

    # -- physics -------------------------------------------------------------

    def step(self, dt):
        """Move the simulated motor forward in time by dt seconds."""
        mode = self.get("operating_mode")

        if self.get("torque_enable") == 0:
            # Motor is free: it slowly coasts to a stop.
            target_velocity = 0.0
            time_constant = FREE_TIME_CONSTANT
        elif mode == 1:
            # Velocity mode: turn at the goal velocity.
            target_velocity = self.get("goal_velocity")
            time_constant = VELOCITY_TIME_CONSTANT
        elif mode == 2:
            # PWM mode: more PWM -> faster. Like the real STS3215, a positive
            # raw PWM turns towards smaller angles (see units.PWM_DIRECTION).
            pwm = units.decode_sign_magnitude(self.get("goal_time"), 10)
            target_velocity = -pwm / 1000 * MAX_SPEED
            time_constant = VELOCITY_TIME_CONSTANT
        else:
            # Position mode: speed is proportional to the remaining distance.
            # The encoder only knows one turn, so position mode works within one turn.
            self.position = self.position % units.STEPS_PER_REVOLUTION
            # The goal is given in "offset" coordinates, like present_position.
            goal_on_encoder = self.get("goal_position") + self.get("homing_offset")
            error = goal_on_encoder - self.position
            speed_limit = self.get("goal_velocity") or MAX_SPEED
            # A higher P gain (p_coefficient, factory value 32) pulls harder.
            gain = POSITION_GAIN * self.get("p_coefficient") / 32
            target_velocity = gain * error
            target_velocity = max(-speed_limit, min(speed_limit, target_velocity))
            time_constant = VELOCITY_TIME_CONSTANT

        target_velocity = max(-MAX_SPEED, min(MAX_SPEED, target_velocity))

        # First-order lag: close a part of the gap to the target speed each step.
        self.velocity += (target_velocity - self.velocity) * min(dt / time_constant, 1.0)
        self.position += self.velocity * dt
        self.update_present_values(target_velocity)

    def update_present_values(self, target_velocity):
        """Write the simulated state into the read-only registers."""
        # The real encoder only knows one turn: 0...4095, then it starts over.
        # homing_offset shifts the zero point: present = encoder - offset.
        # Like the real STS3215, only in position mode.
        present = round(self.position)
        if self.get("operating_mode") == 0:
            present -= self.get("homing_offset")
        self.set("present_position", present % units.STEPS_PER_REVOLUTION)
        self.set("present_velocity", round(self.velocity))

        # "Load": how far the motor is from the speed it wants -> how hard it works.
        load = (target_velocity - self.velocity) / MAX_SPEED * 1000
        load = max(-1000, min(1000, round(load)))
        self.set("present_load", load)

        amps = 0.05 + 1.5 * abs(load) / 1000
        self.set("present_current", round(amps / units.CURRENT_AMPS_PER_STEP))
        self.set("moving", 1 if abs(self.velocity) > 20 else 0)


class SimPort:
    """A bus full of simulated motors. Same methods as FeetechPort."""

    def __init__(self, motor_ids=(1, 2, 3)):
        self.name = "sim"
        self.motors = {}
        for motor_id in motor_ids:
            self.motors[motor_id] = SimMotor(motor_id)
        # IDs given twice, e.g. SimPort((1, 1)): like two real motors with the
        # same ID. Only one of them is simulated, but id_used_twice() tells.
        self.used_twice = {motor_id for motor_id in motor_ids if list(motor_ids).count(motor_id) > 1}
        self.last_update = time.perf_counter()

    def close(self):
        """Nothing to close: there is no cable."""

    # -- the six port methods (what they do: see feetech_port.py) -----------

    def ping(self, motor_id, timeout_ms=None):
        self.advance_time()
        if motor_id in self.motors:
            return self.motors[motor_id].get("model_number")
        return None

    def read(self, motor_id, address, size):
        self.advance_time()
        motor = self.get_motor(motor_id)
        return motor.memory[address:address + size]

    def write(self, motor_id, address, data):
        self.advance_time()
        motor = self.get_motor(motor_id)
        motor.memory[address:address + len(data)] = data

        # If the ID register was changed, the motor now answers to its new ID.
        new_id = motor.get("id")
        if new_id != motor_id:
            del self.motors[motor_id]
            self.motors[new_id] = motor

    def sync_read(self, motor_ids, address, size):
        answers = {}
        for motor_id in motor_ids:
            answers[motor_id] = self.read(motor_id, address, size)
        return answers

    def sync_write(self, motor_ids, address, data_per_id):
        for motor_id in motor_ids:
            self.write(motor_id, address, data_per_id[motor_id])

    def factory_reset(self, motor_id):
        self.advance_time()
        motor = self.get_motor(motor_id)
        motor.factory_reset()

    def id_used_twice(self, motor_id):
        return motor_id in self.used_twice

    # -- helpers -----------------------------------------------------------

    def get_motor(self, motor_id):
        """The SimMotor with this ID. Raises NoResponseError like a real bus if there is none."""
        if motor_id not in self.motors:
            raise NoResponseError(motor_id)
        return self.motors[motor_id]

    def advance_time(self):
        """Run the physics of all motors up to the current time."""
        now = time.perf_counter()
        # After a long pause, only simulate the last second: by then every
        # motor has settled anyway, and we save a lot of calculation.
        remaining = min(now - self.last_update, 1.0)
        self.last_update = now

        while remaining > 0:
            dt = min(remaining, LONGEST_STEP)
            for motor in self.motors.values():
                motor.step(dt)
            remaining -= dt
