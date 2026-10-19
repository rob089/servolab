"""
What the documentation shows, read straight from the servolab package.

ServoScope's documentation page (docs_view.py) and the documentation website
(docs/gen_pages.py in the repository) both use this module, so they always
show the same guides and the same API entries. It does not need NiceGUI.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import servolab

DOCS_DIR = Path(servolab.__file__).parent / "docs"

# The guides in servolab/docs/, in this order: (file name, title)
GUIDES = [
    ("getting_started.md", "Getting started"),
    ("modes_and_units.md", "Modes & units"),
    ("imu.md", "IMU"),
    ("network.md", "Robots over WiFi"),
    ("simulation.md", "Simulation"),
    ("troubleshooting.md", "Troubleshooting"),
]

# What appears in the API reference, in this order: (heading, prefix shown in code, object, members)
API = [
    ("Module", "servolab.", servolab, ["connect", "list_ports"]),
    ("Bus", "bus.", servolab.Bus, [
        "motors", "sensors", "__getitem__", "scan", "read_feedback", "write_positions", "write_velocities",
        "write_pwms", "move_to", "read_register", "write_register", "write_registers",
        "sync_write_register", "sync_write_registers", "change_id", "factory_reset", "torque_off_all", "disconnect",
    ]),
    ("Motor", "m.", servolab.Motor, [
        "id", "position", "velocity", "pwm", "current", "load", "voltage", "temperature", "moving", "status",
        "torque_enabled", "mode", "pid", "info", "move_to", "wait_until_arrived", "set_zero", "factory_reset",
        "read_register", "write_register", "save_to_eeprom",
    ]),
    ("Imu", "imu.", servolab.Imu, [
        "id", "read", "acceleration", "angular_velocity", "quaternion", "gyro_range", "acc_range",
        "sample_rate", "info", "read_register", "write_register", "save_to_eeprom", "factory_reset",
    ]),
    ("Feedback", "fb.", servolab.Feedback, ["of"]),
    ("Recorder", "rec.", servolab.Recorder, ["add", "__getitem__", "plot", "save"]),
    ("LivePlot", "live.", servolab.LivePlot, ["add"]),
    ("Rate", "rate.", servolab.Rate, ["sleep"]),
]

# Attributes without a docstring of their own (plain dicts set in Bus.__init__)
ATTRIBUTE_DOCS = {
    "motors": "Dict of all motors found by the last scan: {ID: Motor}.",
    "sensors": "Dict of all sensors (IMUs) found by the last scan: {ID: Imu}.",
}


def find_examples_dir() -> Path | None:
    """examples/ next to src/ in a source checkout (not part of an installed wheel)."""
    candidate = Path(servolab.__file__).resolve().parents[2] / "examples"
    return candidate if candidate.is_dir() else None


def api_entry(prefix: str, obj, member: str) -> tuple[str, str]:
    """(signature, docstring) of one API member, as shown in the reference.

    Examples: ("m.position   (read / write)", "Present position in rad ..."),
              ("bus.scan(ids=range(0, 253))", "Ask every ID ..."),
              ("bus[device_id]", "bus[1] gives you ...").
    """
    if member in ATTRIBUTE_DOCS:
        return f"{prefix}{member}", ATTRIBUTE_DOCS[member]
    if member == "__getitem__":
        index = "device_id" if obj is servolab.Bus else "name"
        return f"{prefix.rstrip('.')}[{index}]", inspect.getdoc(getattr(obj, member)) or ""
    attribute = inspect.getattr_static(obj, member)
    if isinstance(attribute, property):
        writable = attribute.fset is not None
        signature = f"{prefix}{member}" + ("   (read / write)" if writable else "   (read only)")
        return signature, inspect.getdoc(attribute) or ""
    function = getattr(obj, member)
    params = str(inspect.signature(function)).replace("(self, ", "(").replace("(self)", "()")
    return f"{prefix}{member}{params}", inspect.getdoc(function) or ""


def toc_label(prefix: str, obj, member: str) -> str:
    """Short name of an API member for a table of contents, e.g. "scan()" or "position"."""
    if member in ATTRIBUTE_DOCS:
        return member
    if member == "__getitem__":
        return f"{prefix.rstrip('.')}[…]"
    if isinstance(inspect.getattr_static(obj, member), property):
        return member
    return f"{member}()"


def first_paragraph(text: str) -> str:
    """Everything before the first empty line, e.g. the summary of a class docstring."""
    return text.strip().split("\n\n")[0]
