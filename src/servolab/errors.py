"""
errors.py - what can go wrong, and what to do about it.

All errors that servolab raises are subclasses of `ServoLabError`.
So if you want to catch "anything servolab complains about", write:

    try:
        m.position = 1.0
    except servolab.ServoLabError as error:
        print("Something went wrong:", error)

This file also knows how to turn the motor's "status" byte into readable words.
"""


class ServoLabError(Exception):
    """Base class for every error raised by servolab."""


def missing_extra(package, extra):
    """Error for an optional package that is not installed (see pyproject.toml, extras)."""
    return ServoLabError(f'This needs {package}. Install it: uv add "servolab[{extra}]" (or pip install)')


class PortError(ServoLabError):
    """The serial port could not be opened, or the bus is already disconnected."""


class NoResponseError(ServoLabError):
    """A motor (or several) did not answer in time."""

    def __init__(self, motor_ids):
        # Accept a single ID as well as a list of IDs.
        if isinstance(motor_ids, int):
            motor_ids = [motor_ids]
        self.motor_ids = motor_ids
        ids_text = ", ".join(str(motor_id) for motor_id in motor_ids)
        super().__init__(f"Motor {ids_text} does not answer. Check power, cable and ID (bus.scan()).")


class CommunicationError(ServoLabError):
    """A message on the bus was garbled or could not be sent."""


class DuplicateIdError(ServoLabError):
    """Two or more devices on the bus have the same ID (found by bus.scan())."""

    def __init__(self, ids):
        self.ids = ids
        ids_text = ("ID " if len(ids) == 1 else "IDs ") + ", ".join(str(device_id) for device_id in ids)
        super().__init__(f"Several devices have {ids_text}. Connect them one at a time and give each its own ID.")


class RegisterError(ServoLabError):
    """A register name is unknown, read-only, or the value is out of range."""


# ---------------------------------------------------------------------------
# Status bits
# ---------------------------------------------------------------------------
# Every motor has a "status" register (address 65). Each bit in it is a
# warning light. If the bit is 1, that problem is active right now.
#
#   bit 0 (value 1)  : supply voltage too low or too high
#   bit 1 (value 2)  : problem with the angle sensor
#   bit 2 (value 4)  : motor is too hot
#   bit 3 (value 8)  : current too high
#   bit 5 (value 32) : overloaded for too long
STATUS_BITS = {
    1: "voltage",
    2: "angle_sensor",
    4: "overheat",
    8: "overcurrent",
    32: "overload",
}


def decode_status(status_byte):
    """Turn the status byte into a list of problem names.

    Example:
        decode_status(0)   -> []                         (all fine)
        decode_status(4)   -> ['overheat']
        decode_status(36)  -> ['overheat', 'overload']   (36 = 4 + 32)
    """
    problems = []
    for bit_value, name in STATUS_BITS.items():
        if status_byte & bit_value:  # "&" checks whether this bit is set
            problems.append(name)
    return problems
