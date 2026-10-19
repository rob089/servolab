"""
registers.py - the "memory table" inside each motor (and each IMU).

A Feetech motor is controlled by reading and writing numbered memory cells,
called registers. For example:
    address 42 = goal position   (write here -> the motor moves)
    address 56 = present position (read here -> where is the motor now?)

This file lists every register of the STS3215 motor and of the XIAO IMU with
its address, its size and what it does. The rest of servolab looks registers
up here by name, so you can write  m.read_register("present_temperature")
instead of remembering "address 63".

Two kinds of memory:
- "eeprom": settings that can be kept after power-off (ID, limits, gains ...)
- "ram":    live values, lost after power-off (goal position, torque on/off ...)

Source: Feetech STS/SMS memory table, cross-checked with the Feetech SDK
and with LeRobot's table.
"""

from dataclasses import dataclass

from servolab.errors import RegisterError


@dataclass
class Register:
    """Description of one register (one row of the memory table)."""

    name: str            # name used in servolab, e.g. "goal_position"
    address: int         # where it lives in the motor's memory
    size: int            # number of bytes: 1 (0...255) or 2 (0...65535)
    access: str          # "r" = read only,  "rw" = read and write
    memory: str          # "eeprom" or "ram" (see top of this file)
    group: str           # topic, used to sort registers in ServoScope
    unit: str            # unit of the RAW value, for display only
    description: str     # what it does, in plain words
    sign_bit: int | None = None  # set if the value can be negative (see units.py)


# Column order:  name, address, size, access, memory, group, unit, description [, sign_bit]
STS3215_REGISTERS = [
    # --- identity -----------------------------------------------------------
    Register("firmware_major", 0, 1, "r", "eeprom", "identity", "",
             "Firmware version, main number."),
    Register("firmware_minor", 1, 1, "r", "eeprom", "identity", "",
             "Firmware version, sub number."),
    Register("model_number", 3, 2, "r", "eeprom", "identity", "",
             "Model number. 777 = STS3215."),
    Register("id", 5, 1, "rw", "eeprom", "identity", "",
             "Address of the motor on the bus (0...253). Every motor on one bus needs its own ID."),
    Register("baud_rate", 6, 1, "rw", "eeprom", "identity", "",
             "Bus speed. 0 = 1 Mbit/s (default, used by servolab). Other values: see Feetech manual."),
    Register("return_delay_time", 7, 1, "rw", "eeprom", "identity", "2 us",
             "How long the motor waits before it answers."),
    Register("response_status_level", 8, 1, "rw", "eeprom", "identity", "",
             "0 = answer only read and ping, 1 = answer every instruction."),

    # --- limits -------------------------------------------------------------
    Register("min_position_limit", 9, 2, "rw", "eeprom", "limits", "steps",
             "Smallest allowed goal position in position mode. Both limits 0 = no limits (multi-turn)."),
    Register("max_position_limit", 11, 2, "rw", "eeprom", "limits", "steps",
             "Largest allowed goal position in position mode."),
    Register("max_temperature_limit", 13, 1, "rw", "eeprom", "limits", "degC",
             "Above this temperature the motor protects itself."),
    Register("max_voltage_limit", 14, 1, "rw", "eeprom", "limits", "0.1 V",
             "Above this supply voltage the motor reports an error."),
    Register("min_voltage_limit", 15, 1, "rw", "eeprom", "limits", "0.1 V",
             "Below this supply voltage the motor reports an error."),
    Register("max_torque_limit", 16, 2, "rw", "eeprom", "limits", "0.1 %",
             "Maximum torque, 1000 = 100 %. Copied to torque_limit when the motor powers up."),

    # --- protection -----------------------------------------------------------
    Register("phase", 18, 1, "rw", "eeprom", "protection", "",
             "Special function bits. Do not change unless you know exactly why."),
    Register("unloading_condition", 19, 1, "rw", "eeprom", "protection", "bits",
             "Which problems switch the torque off (one bit per problem, see errors.py)."),
    Register("led_alarm_condition", 20, 1, "rw", "eeprom", "protection", "bits",
             "Which problems make the LED blink (one bit per problem, see errors.py)."),
    Register("protection_current", 28, 2, "rw", "eeprom", "protection", "6.5 mA",
             "Current limit of the over-current protection."),
    Register("protective_torque", 34, 1, "rw", "eeprom", "protection", "%",
             "Torque that is left after the overload protection kicked in."),
    Register("protection_time", 35, 1, "rw", "eeprom", "protection", "10 ms",
             "How long an overload may last before the protection kicks in."),
    Register("overload_torque", 36, 1, "rw", "eeprom", "protection", "%",
             "Torque above which the motor counts as overloaded."),
    Register("over_current_protection_time", 38, 1, "rw", "eeprom", "protection", "10 ms",
             "How long too much current may flow before the protection kicks in."),

    # --- control (internal controller of the motor) --------------------------
    Register("p_coefficient", 21, 1, "rw", "eeprom", "control", "",
             "P gain of the internal position controller."),
    Register("d_coefficient", 22, 1, "rw", "eeprom", "control", "",
             "D gain of the internal position controller."),
    Register("i_coefficient", 23, 1, "rw", "eeprom", "control", "",
             "I gain of the internal position controller."),
    Register("minimum_startup_force", 24, 2, "rw", "eeprom", "control", "0.1 %",
             "Smallest output the motor uses, to overcome static friction."),
    Register("cw_dead_zone", 26, 1, "rw", "eeprom", "control", "steps",
             "Position error (clockwise) that still counts as 'arrived'."),
    Register("ccw_dead_zone", 27, 1, "rw", "eeprom", "control", "steps",
             "Position error (counter-clockwise) that still counts as 'arrived'."),
    Register("angular_resolution", 30, 1, "rw", "eeprom", "control", "",
             "Resolution factor for multi-turn mode. Leave at 1."),
    Register("homing_offset", 31, 2, "rw", "eeprom", "control", "steps",
             "Shifts the zero point: present_position = encoder - homing_offset "
             "(the motor does this only in position mode, servolab in the other modes).", sign_bit=11),
    Register("operating_mode", 33, 1, "rw", "eeprom", "control", "",
             "0 = position, 1 = velocity, 2 = PWM (open loop)."),
    Register("velocity_p_coefficient", 37, 1, "rw", "eeprom", "control", "",
             "P gain of the internal velocity controller (velocity mode)."),
    Register("velocity_i_coefficient", 39, 1, "rw", "eeprom", "control", "",
             "I gain of the internal velocity controller (velocity mode)."),

    # --- commands (what the motor should do now) -----------------------------
    Register("torque_enable", 40, 1, "rw", "ram", "command", "",
             "1 = motor is powered and holds/moves, 0 = motor is free (turn it by hand)."),
    Register("acceleration", 41, 1, "rw", "ram", "command", "100 steps/s^2",
             "Acceleration for movements. 0 = as fast as possible."),
    Register("goal_position", 42, 2, "rw", "ram", "command", "steps",
             "Position mode: where the motor should go.", sign_bit=15),
    Register("goal_time", 44, 2, "rw", "ram", "command", "ms",
             "Position mode: duration of a move (0 = use goal_velocity). "
             "PWM mode: the PWM output -1000...1000 (bit 10 = direction)."),
    Register("goal_velocity", 46, 2, "rw", "ram", "command", "steps/s",
             "Velocity mode: speed to turn at. Position mode: maximum speed of a move.", sign_bit=15),
    Register("torque_limit", 48, 2, "rw", "ram", "command", "0.1 %",
             "Current torque limit, 1000 = 100 %."),
    Register("lock", 55, 1, "rw", "ram", "command", "",
             "0 = EEPROM writes are kept after power-off, 1 = they are lost (default)."),

    # --- state (what the motor is doing now, read only) ----------------------
    Register("present_position", 56, 2, "r", "ram", "state", "steps",
             "Where the motor is right now.", sign_bit=15),
    Register("present_velocity", 58, 2, "r", "ram", "state", "steps/s",
             "How fast the motor turns right now.", sign_bit=15),
    Register("present_load", 60, 2, "r", "ram", "state", "0.1 %",
             "How hard the motor is working, 1000 = 100 %.", sign_bit=10),
    Register("present_voltage", 62, 1, "r", "ram", "state", "0.1 V",
             "Supply voltage."),
    Register("present_temperature", 63, 1, "r", "ram", "state", "degC",
             "Temperature inside the motor."),
    Register("status", 65, 1, "r", "ram", "state", "bits",
             "Active problems, one bit per problem (see errors.py)."),
    Register("moving", 66, 1, "r", "ram", "state", "",
             "1 while the motor is moving, 0 when it stands still."),
    Register("present_current", 69, 2, "r", "ram", "state", "6.5 mA",
             "Motor current."),

    # --- factory settings ----------------------------------------------------
    Register("moving_velocity_threshold", 80, 1, "rw", "eeprom", "factory", "",
             "Speed below which the motor counts as standing still."),
    Register("maximum_velocity_limit", 84, 1, "rw", "eeprom", "factory", "",
             "Factory speed limit."),
    Register("maximum_acceleration", 85, 1, "rw", "eeprom", "factory", "",
             "Factory acceleration limit."),
]


# The XIAO IMU: our own IMU for the bus (a Seeed XIAO nRF52840 Sense with its
# own firmware, see firmware/xiao_imu/ in the servolab repository). It copies the layout of
# Feetech's bus IMU. Its measurements start at address 56 like the motors'
# state, so one sync read can ask motors and IMUs together.
XIAO_IMU_REGISTERS = [
    # --- identity -----------------------------------------------------------
    Register("firmware_major", 0, 1, "r", "eeprom", "identity", "",
             "Firmware version, main number."),
    Register("firmware_minor", 1, 1, "r", "eeprom", "identity", "",
             "Firmware version, sub number."),
    Register("model_number", 3, 2, "r", "eeprom", "identity", "",
             "Model number. 2026 = XIAO IMU."),
    Register("id", 5, 1, "rw", "eeprom", "identity", "",
             "Address of the IMU on the bus (0...253). New IMUs have ID 100."),
    Register("baud_rate", 6, 1, "rw", "eeprom", "identity", "",
             "Bus speed. 0 = 1 Mbit/s (default, used by servolab), same codes as the motors."),

    # --- settings -------------------------------------------------------------
    Register("gyro_range", 11, 1, "rw", "eeprom", "settings", "",
             "Measuring range of the gyro: 0 = 250, 1 = 500, 2 = 1000, 3 = 2000 deg/s (default)."),
    Register("acc_range", 12, 1, "rw", "eeprom", "settings", "",
             "Measuring range of the accelerometer: 0 = 2, 1 = 4, 2 = 8 (default), 3 = 16 g."),
    Register("sample_rate", 13, 1, "rw", "eeprom", "settings", "",
             "Measurements per second: 0 = 26, 1 = 52, 2 = 104, 3 = 208, 4 = 416 (default), 5 = 833 Hz."),

    # --- commands -------------------------------------------------------------
    Register("lock", 55, 1, "rw", "ram", "command", "",
             "0 = EEPROM writes are kept after power-off, 1 = they are lost (default)."),

    # --- state (measurements, read only) ---------------------------------------
    Register("quaternion_x", 56, 2, "r", "ram", "state", "half float",
             "Orientation, x part of the quaternion (w is not sent: w = sqrt(1 - x^2 - y^2 - z^2))."),
    Register("quaternion_y", 58, 2, "r", "ram", "state", "half float",
             "Orientation, y part of the quaternion."),
    Register("quaternion_z", 60, 2, "r", "ram", "state", "half float",
             "Orientation, z part of the quaternion."),
    Register("angular_velocity_x", 62, 2, "r", "ram", "state", "mrad/s",
             "Gyro: turning speed around the x axis.", sign_bit=15),
    Register("angular_velocity_y", 65, 2, "r", "ram", "state", "mrad/s",
             "Gyro: turning speed around the y axis.", sign_bit=15),
    Register("angular_velocity_z", 68, 2, "r", "ram", "state", "mrad/s",
             "Gyro: turning speed around the z axis.", sign_bit=15),
    Register("acceleration_x", 71, 2, "r", "ram", "state", "mg",
             "Accelerometer, x axis (1 mg = 1/1000 of gravity).", sign_bit=15),
    Register("acceleration_y", 74, 2, "r", "ram", "state", "mg",
             "Accelerometer, y axis.", sign_bit=15),
    Register("acceleration_z", 77, 2, "r", "ram", "state", "mg",
             "Accelerometer, z axis.", sign_bit=15),
]


# Which model number belongs to which device, and which table it uses.
# (The STS3250 is a stronger motor with the same memory table.)
MODEL_NAMES = {
    777: "STS3215",
    2825: "STS3250",
    2026: "XIAO IMU",
}

REGISTER_TABLES = {
    "STS3215": STS3215_REGISTERS,
    "STS3250": STS3215_REGISTERS,
    "XIAO IMU": XIAO_IMU_REGISTERS,
}

# Devices that are IMUs, not motors. bus.scan() puts them into bus.sensors.
IMU_MODELS = ["XIAO IMU"]


def find_register(model_name, register_name):
    """Look up a register by name, e.g. find_register("STS3215", "goal_position")."""
    if model_name not in REGISTER_TABLES:
        raise_unknown_model(model_name)
    for register in REGISTER_TABLES[model_name]:
        if register.name == register_name:
            return register
    raise RegisterError(f"The {model_name} has no register '{register_name}' (see servolab/registers.py).")


def allowed_range(register):
    """Smallest and largest value you can write into a register.

    Example: a 1-byte register allows 0...255,
             goal_position (2 bytes, sign bit 15) allows -32767...32767.
    """
    if register.sign_bit is not None:
        largest = 2 ** register.sign_bit - 1
        return -largest, largest
    return 0, 256 ** register.size - 1


def raise_unknown_model(model_name):
    """Raise a RegisterError that lists the models servolab knows."""
    raise RegisterError(f"Unknown model '{model_name}'. Known: {', '.join(REGISTER_TABLES)}.")
