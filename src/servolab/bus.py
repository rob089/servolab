"""
bus.py - all motors (and sensors) on one daisy chain.

Feetech motors are connected in a chain ("bus"). Every motor has an ID, and
every message on the cable says which ID it is meant for. Other devices can
sit on the same chain with their own ID, e.g. an IMU (see imu.py).

    bus = servolab.connect()     # opens the port and finds all motors
    bus.motors                   # {1: <Motor 1: STS3215>, 2: ...}
    bus.sensors                  # {100: <Imu 100: XIAO IMU>}   (if there are any)
    m = bus[1]                   # the motor with ID 1 (see motor.py)
    imu = bus[100]               # the IMU with ID 100 (see imu.py)

Note: bus[1] means "the device with ID 1", not "element 1 of a list".
The bus works like a dict: bus.motors = {ID: Motor}. New motors have ID 1.

    fb = bus.read_feedback()     # state of ALL motors (and sensors) with one message
    bus.write_positions({1: 0.5, 2: -0.5})   # move several motors at once
    bus.write_positions(fb.position + 0.1)   # ... or with an array, ordered like fb.ids
    bus.move_to([0.5, -0.5], speed=1.0)      # like m.move_to(), for several motors

The bus translates between register names (registers.py) and the bytes that
the port (ports/) sends over the cable.
"""

import atexit
import threading
import time

import numpy as np

from servolab import units
from servolab.errors import (
    DuplicateIdError,
    NoResponseError,
    PortError,
    RegisterError,
    ServoLabError,
    decode_status,
)
from servolab.feedback import Feedback
from servolab.imu import MEASUREMENTS_SIZE, MEASUREMENTS_START, Imu, feedback_from_block
from servolab.motor import Motor
from servolab.registers import IMU_MODELS, MODEL_NAMES, REGISTER_TABLES, allowed_range, find_register

SCAN_TIMEOUT_MS = 10     # how long to wait for each ID while scanning

# read_feedback() reads one block of registers: from present_position
# (address 56) up to present_current (address 69 + 70) = 15 bytes.
# With IMUs on the bus it reads 23 bytes, because the IMU's measurements
# (imu.py) start at the same address but are longer.
FEEDBACK_START = 56
FEEDBACK_SIZE = 15


class Bus:
    """A connection to a chain of motors (and sensors)."""

    def __init__(self, port):
        self.port = port            # FeetechPort, SimPort, MujocoPort or NetworkPort (see ports/)

        # Only for a simulated robot, connect("sim:so102"): tools a real robot
        # doesn't have, e.g. bus.sim.tcp() = where the gripper really is.
        self.sim = port if port.name.startswith("sim:") else None
        self.motors = {}            # motor ID -> Motor
        self.sensors = {}           # sensor ID -> Imu (IMUs are the only sensors so far)
        self.connected = True

        # read_feedback() asks motors and sensors with one message. If a bus
        # cannot do that, it notices and asks them one after another instead.
        self.combined_feedback = True
        self.start_time = time.perf_counter()

        # The lock makes sure only one message is on the cable at a time,
        # even if two parts of a program (e.g. ServoScope and a plot) use the
        # bus at the same moment. "RLock" = the same thread may take it twice.
        self.lock = threading.RLock()

        # Switch all motors off when Python exits, no matter how.
        atexit.register(self.disconnect)

    def __repr__(self):
        state = "connected" if self.connected else "disconnected"
        sensors = f", sensors {list(self.sensors)}" if self.sensors else ""
        return f"<Bus on {self.port.name}, {state}, motors {list(self.motors)}{sensors}>"

    def __getitem__(self, device_id):
        """bus[1] gives you the motor (or sensor) with ID 1 (an ID, not a list index)."""
        if device_id in self.motors:
            return self.motors[device_id]
        if device_id in self.sensors:
            return self.sensors[device_id]
        found = list(self.motors) + list(self.sensors)
        raise PortError(f"No device with ID {device_id} (found: {found}). New device? Call bus.scan().")

    # =======================================================================
    # Finding motors
    # =======================================================================

    def scan(self, ids=range(0, 253)):
        """Ask every ID whether a device is there. Returns the list of found IDs.

        Motors end up in bus.motors, IMUs in bus.sensors.

        Takes about 2.5 s for all 253 IDs. If you know your IDs, scan fewer:
        bus.scan(range(1, 7))

        Raises DuplicateIdError if two devices answer to the same ID.
        """
        self.check_connected()
        found = {}
        with self.lock:
            for motor_id in ids:
                model_number = self.port.ping(motor_id, timeout_ms=SCAN_TIMEOUT_MS)
                if model_number is not None:
                    found[motor_id] = model_number
            # Two devices with the same ID both answer, and every command reaches
            # both of them: nothing works reliably. So stop here with a clear error.
            used_twice = [device_id for device_id in found if self.port.id_used_twice(device_id)]
        if used_twice:
            raise DuplicateIdError(used_twice)

        self.motors = {}
        self.sensors = {}
        for device_id, model_number in found.items():
            model = MODEL_NAMES.get(model_number, f"unknown model {model_number}")
            if model in IMU_MODELS:
                self.sensors[device_id] = Imu(self, device_id, model)
            else:
                self.motors[device_id] = Motor(self, device_id, model)

        # Now that the bus knows its motors, ask each one for its mode.
        for motor_id in self.known_motor_ids():
            self.motors[motor_id].update_mode()
        return list(found)

    # =======================================================================
    # Registers of one motor
    # =======================================================================

    def read_register(self, motor_id, name):
        """Read one register of one motor by name. Returns the raw value (int)."""
        self.check_connected()
        register = self.find_register(motor_id, name)
        with self.lock:
            data = self.port.read(motor_id, register.address, register.size)
        return self.decode(register, data)

    def write_register(self, motor_id, name, value, save=False):
        """Write one register of one motor by name. `value` is raw (int).

        save=True: also keep the value after power-off (EEPROM registers only).
        """
        self.check_connected()
        if name == "id":
            self.change_id(motor_id, value)   # needs special care, see below
            return
        register = self.find_register(motor_id, name)
        if register.access != "rw":
            raise RegisterError(f"'{name}' is read-only.")
        data = self.encode(register, value)

        with self.lock:
            if save:
                # Unlock the EEPROM, write, lock again (see the "lock" register)
                lock = find_register(self[motor_id].model, "lock")
                self.port.write(motor_id, lock.address, [0])
                self.port.write(motor_id, register.address, data)
                self.port.write(motor_id, lock.address, [1])
            else:
                self.port.write(motor_id, register.address, data)

    def write_registers(self, motor_id, values):
        """Write several registers that lie next to each other with ONE message.

        values = {name: raw value, ...}, in any order. The motor gets all of
        them at the same moment, e.g. speed and goal of a move together.
        """
        self.check_connected()
        address, data = self.encode_block(motor_id, values)
        with self.lock:
            self.port.write(motor_id, address, data)

    def change_id(self, old_id, new_id):
        """Give a motor (or sensor) a new ID. It is saved permanently in the device.

        Usually you just write  bus[1].id = 2  which calls this function.
        """
        self.check_connected()
        new_id = int(new_id)
        if new_id == old_id:
            return
        if not 0 <= new_id <= 253:
            raise RegisterError(f"IDs go from 0 to 253, {new_id} is not allowed.")
        device = self[old_id]
        with self.lock:
            taken = new_id in self.motors or new_id in self.sensors
            if taken or self.port.ping(new_id) is not None:
                raise RegisterError(f"ID {new_id} is already used by another device.")
            id_register = find_register(device.model, "id")
            lock = find_register(device.model, "lock")

            self.port.write(old_id, lock.address, [0])     # unlock EEPROM -> change is kept
            try:
                self.port.write(old_id, id_register.address, [new_id])
            except NoResponseError:
                pass   # the motor may already answer with its new ID; we check below
            # From here on the motor only listens to its NEW ID.
            if self.port.ping(new_id) is None:
                raise NoResponseError(new_id)
            self.port.write(new_id, lock.address, [1])     # lock EEPROM again

        # Keep our lists in step with the real device.
        devices = self.motors if old_id in self.motors else self.sensors
        del devices[old_id]
        device._id = new_id
        devices[new_id] = device

    def factory_reset(self, device_id, keep_zero=True):
        """Put a motor (or IMU) back to its factory settings. Saved permanently.

        Uses the device's own reset instruction, so you get exactly the values
        it came with: limits, gains, mode, protection ...
        The device keeps its ID. A motor also keeps its zero position
        (see m.set_zero()), unless keep_zero=False.

        Usually you just write  bus[1].factory_reset()  which calls this function.
        """
        self.check_connected()
        device = self[device_id]
        is_motor = device_id in self.motors
        with self.lock:
            if is_motor and keep_zero:
                # The reset sets homing_offset to 0: remember it, to write it back afterwards.
                homing = find_register(device.model, "homing_offset")
                zero_bytes = self.port.read(device_id, homing.address, homing.size)

            try:
                self.port.factory_reset(device_id)
            except NoResponseError:
                pass   # the device may still be busy with the reset; we wait for it below
            self.wait_after_reset(device_id)

            if is_motor and keep_zero:
                lock = find_register(device.model, "lock")
                self.port.write(device_id, lock.address, [0])      # unlock EEPROM -> change is kept
                self.port.write(device_id, homing.address, zero_bytes)
                self.port.write(device_id, lock.address, [1])      # lock EEPROM again

    def wait_after_reset(self, device_id, timeout=1.0):
        """After a reset the device needs a moment before it answers again."""
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if self.port.ping(device_id) is not None:
                return
            time.sleep(0.05)
        raise NoResponseError(device_id)

    # =======================================================================
    # Several motors at once
    # =======================================================================

    def read_feedback(self, ids=None):
        """Read the state of all motors and sensors with ONE message. Returns a Feedback.

        ids: only read these devices, e.g. [1, 2]. None = all motors and sensors.

        Example:
            fb = bus.read_feedback()
            fb.position                     # array, in rad, sorted like fb.ids
            fb.sensors[100].acceleration    # the IMU with ID 100, in m/s^2
        """
        self.check_connected()
        if ids is None:
            ids = self.known_motor_ids()
            sensor_ids = self.known_sensor_ids()
        else:
            sensor_ids = sorted(device_id for device_id in ids if device_id in self.sensors)
            ids = sorted(device_id for device_id in ids if device_id not in self.sensors)
        with self.lock:
            blocks = self.read_feedback_blocks(ids, sensor_ids)

        position, velocity, current, load, voltage, temperature, status = [], [], [], [], [], [], []
        for motor_id in ids:
            block = blocks[motor_id]
            model = self.motors[motor_id].model
            raw_position = self.value_in_block(model, block, "present_position")
            position.append(units.steps_to_rad(self.motors[motor_id].present_steps(raw_position)))
            velocity.append(units.steps_per_s_to_rad_per_s(self.value_in_block(model, block, "present_velocity")))
            current.append(units.raw_to_amps(self.value_in_block(model, block, "present_current")))
            load.append(units.raw_to_fraction(self.value_in_block(model, block, "present_load")))
            voltage.append(units.raw_to_volts(self.value_in_block(model, block, "present_voltage")))
            temperature.append(self.value_in_block(model, block, "present_temperature"))
            status.append(decode_status(self.value_in_block(model, block, "status")))

        sensors = {}
        for sensor_id in sensor_ids:
            sensors[sensor_id] = feedback_from_block(self, self.sensors[sensor_id].model, blocks[sensor_id])

        return Feedback(
            time=self.elapsed_time(),
            ids=ids,
            position=np.array(position),
            velocity=np.array(velocity),
            current=np.array(current),
            load=np.array(load),
            voltage=np.array(voltage),
            temperature=np.array(temperature),
            status=status,
            sensors=sensors,
        )

    def read_feedback_blocks(self, motor_ids, sensor_ids):
        """Read the raw feedback bytes for read_feedback(). Returns {ID: bytes}.

        With sensors, ONE sync read asks everybody for 23 bytes from address 56
        (the motors' state is shorter, the extra bytes are ignored). Sensors
        come last in the list, as in Feetech's own example. If that fails, but
        asking motors and sensors one after another works, the bus remembers
        it and from then on always asks separately (slower, but it works).
        """
        if not sensor_ids:
            return self.port.sync_read(motor_ids, FEEDBACK_START, FEEDBACK_SIZE)

        combined_failed = False
        if self.combined_feedback:
            try:
                return self.port.sync_read(motor_ids + sensor_ids, FEEDBACK_START, MEASUREMENTS_SIZE)
            except NoResponseError:
                combined_failed = True     # maybe just one device is missing: check below

        blocks = {}
        if motor_ids:
            blocks = self.port.sync_read(motor_ids, FEEDBACK_START, FEEDBACK_SIZE)
        for sensor_id in sensor_ids:
            blocks[sensor_id] = self.port.read(sensor_id, MEASUREMENTS_START, MEASUREMENTS_SIZE)
        if combined_failed:
            self.combined_feedback = False   # everybody answered separately, so ask separately from now on
        return blocks

    def write_positions(self, positions, ids=None):
        """Move several motors at once.

        positions: {motor_id: rad, ...}, or an array/list in the same order
                   as read_feedback().ids (or as `ids`, if given).

        Example:
            bus.write_positions({1: 0.5, 2: -0.5})
            fb = bus.read_feedback()
            bus.write_positions(fb.position + 0.1)
        """
        raw_values = {}
        for motor_id, rad in self.values_per_id(positions, ids).items():
            self[motor_id].require_mode("position")
            raw_values[motor_id] = units.rad_to_steps(rad)
        self.sync_write_register("goal_position", raw_values)

    def write_velocities(self, velocities, ids=None):
        """Set the speed of several motors at once.

        velocities: {motor_id: rad/s, ...}, or an array/list like write_positions().
        """
        raw_values = {}
        for motor_id, rad_per_s in self.values_per_id(velocities, ids).items():
            self[motor_id].require_mode("velocity")
            raw_values[motor_id] = units.rad_per_s_to_steps_per_s(rad_per_s)
        self.sync_write_register("goal_velocity", raw_values)

    def write_pwms(self, pwms, ids=None):
        """Set the PWM of several motors at once.

        pwms: {motor_id: -1.0 ... 1.0, ...}, or an array/list like write_positions().
        """
        raw_values = {}
        for motor_id, fraction in self.values_per_id(pwms, ids).items():
            self[motor_id].require_mode("pwm")
            raw_values[motor_id] = units.pwm_to_raw(fraction)
        self.sync_write_register("goal_time", raw_values)

    def move_to(self, positions, ids=None, speed=None, acceleration=None, wait=False, timeout=10.0):
        """Move several motors at once, optionally with speed and acceleration limits.

        positions:    {motor_id: rad, ...}, or an array/list like write_positions()
        speed:        maximum speed in rad/s, the same for every motor (None = as fast as possible)
        acceleration: in rad/s^2, the same for every motor (None = as fast as possible)
        wait:         True = only return when all motors have arrived
        timeout:      give up waiting after this many seconds

        All motors start at the same time, but each one moves at `speed`, so
        a motor with a shorter way arrives earlier.

        Example:  bus.move_to([0.5, -0.3], ids=[1, 2], speed=1.0, wait=True)
        """
        goals = self.values_per_id(positions, ids)
        acceleration_raw = 0 if acceleration is None else units.acceleration_to_raw(acceleration)
        speed_raw = 0 if speed is None else abs(units.rad_per_s_to_steps_per_s(speed))   # 0 = no limit
        blocks = {}
        for motor_id, rad in goals.items():
            self[motor_id].require_mode("position")
            # All four registers in one message (like Feetech's WritePosEx), so the
            # motor starts the move with the new speed and acceleration.
            # goal_time must be 0: otherwise the motor uses it and ignores the speed.
            blocks[motor_id] = {
                "acceleration": acceleration_raw,
                "goal_position": units.rad_to_steps(rad),
                "goal_time": 0,
                "goal_velocity": speed_raw,
            }
        self.sync_write_registers(blocks)

        if wait:
            start = time.perf_counter()
            for motor_id, rad in goals.items():
                remaining = timeout - (time.perf_counter() - start)
                self[motor_id].wait_until_arrived(rad, remaining)

    def sync_write_registers(self, values_per_id):
        """Write several registers next to each other, of several motors, with ONE message.

        values_per_id = {motor_id: {name: raw value, ...}, ...}. Every motor
        needs the same register names.
        """
        self.check_connected()
        address = None
        data_per_id = {}
        for motor_id, values in values_per_id.items():
            address, data_per_id[motor_id] = self.encode_block(motor_id, values)
        with self.lock:
            self.port.sync_write(list(data_per_id), address, data_per_id)

    def sync_write_register(self, name, raw_values):
        """Write the same register of several motors with ONE message.

        raw_values = {motor_id: raw value, ...}. All motors react at the same time.
        """
        self.check_connected()
        ids = list(raw_values)
        register = self.find_register(ids[0], name)
        data_per_id = {}
        for motor_id in ids:
            data_per_id[motor_id] = self.encode(register, raw_values[motor_id])
        with self.lock:
            self.port.sync_write(ids, register.address, data_per_id)

    def torque_off_all(self):
        """Switch every motor off (they become free to turn by hand)."""
        ids = self.known_motor_ids()
        if ids:
            self.sync_write_register("torque_enable", {motor_id: 0 for motor_id in ids})

    # =======================================================================
    # Connection
    # =======================================================================

    def disconnect(self):
        """Switch all motors off and close the port. Safe to call twice."""
        if not self.connected:
            return
        # We are closing anyway: if something fails here (e.g. the cable was
        # unplugged), ignore it instead of hiding the real problem with a new one.
        try:
            self.torque_off_all()
        except Exception:
            pass
        try:
            self.port.close()
        except Exception:
            pass
        self.connected = False
        atexit.unregister(self.disconnect)

    def read_bytes(self, device_id, address, size):
        """Read `size` raw bytes starting at `address`, e.g. a block of registers."""
        self.check_connected()
        with self.lock:
            return self.port.read(device_id, address, size)

    def elapsed_time(self):
        """Seconds since connect(). Used as the time stamp of feedback."""
        return time.perf_counter() - self.start_time

    def check_connected(self):
        """Raise a helpful error if this bus was disconnected."""
        if not self.connected:
            raise PortError("This bus is disconnected. Connect again with servolab.connect().")

    # =======================================================================
    # Helpers: register names <-> bytes
    # =======================================================================

    def find_register(self, motor_id, name):
        """The Register called `name` in the memory table of this device's model."""
        return find_register(self[motor_id].model, name)

    def values_per_id(self, values, ids=None):
        """Turn {id: value} or an array/list (ordered like `ids`) into {id: value}."""
        if isinstance(values, dict):
            if ids is not None:
                raise ServoLabError("Give either a dict {id: value} or an array with ids=..., not both.")
            return values
        if ids is None:
            ids = self.known_motor_ids()
        else:
            ids = list(ids)     # keep the caller's order: values[i] belongs to ids[i]
        values = np.ravel(values)
        if len(values) != len(ids):
            raise ServoLabError(f"{len(values)} values for {len(ids)} motors {ids}. "
                                f"Order them like fb.ids, or pass ids=[...].")
        return {motor_id: float(value) for motor_id, value in zip(ids, values)}

    def encode_block(self, motor_id, values):
        """{name: raw value} of registers next to each other -> (first address, bytes)."""
        registers = sorted((self.find_register(motor_id, name) for name in values),
                           key=lambda register: register.address)
        start = registers[0].address
        data = []
        for register in registers:
            if register.access != "rw":
                raise RegisterError(f"'{register.name}' is read-only.")
            if register.address != start + len(data):
                raise RegisterError(f"Gap before '{register.name}': registers written together "
                                    "must lie next to each other.")
            data += self.encode(register, values[register.name])
        return start, data

    def known_motor_ids(self):
        """IDs of all motors whose memory table servolab knows, sorted."""
        return sorted(motor_id for motor_id, motor in self.motors.items()
                      if motor.model in REGISTER_TABLES)

    def known_sensor_ids(self):
        """IDs of all sensors, sorted."""
        return sorted(self.sensors)

    def decode(self, register, data):
        """Bytes from the motor -> integer (handles negative numbers)."""
        raw = units.bytes_to_int(data)
        if register.sign_bit is not None:
            return units.decode_sign_magnitude(raw, register.sign_bit)
        return raw

    def encode(self, register, value):
        """Integer -> bytes for the motor. Checks the allowed range first."""
        value = int(value)
        lowest, highest = allowed_range(register)
        if not lowest <= value <= highest:
            raise RegisterError(
                f"{value} does not fit into '{register.name}' (allowed: {lowest} ... {highest})."
            )
        if register.sign_bit is not None:
            value = units.encode_sign_magnitude(value, register.sign_bit)
        return units.int_to_bytes(value, register.size)

    def value_in_block(self, model, block, name):
        """Pick one register out of a block read from address 56 (motor state or IMU measurements)."""
        register = find_register(model, name)
        start = register.address - FEEDBACK_START
        return self.decode(register, block[start:start + register.size])
