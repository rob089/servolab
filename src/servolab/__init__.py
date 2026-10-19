"""
servolab - control Feetech serial bus servos from Python.

Start here:

    import servolab

    bus = servolab.connect()          # find the USB adapter and all motors
    m = bus[1]                        # motor with ID 1
    m.mode = "position"
    m.torque_enabled = True
    m.position = 0.5                  # rad

No hardware at hand?  bus = servolab.connect("sim")          # three pretend motors
                      bus = servolab.connect("sim:so102")    # a whole simulated robot

How the files fit together:

    __init__.py   connect(), list_ports()          <- you are here
    bus.py        Bus: all motors on one cable
    motor.py      Motor: one motor, values in SI units
    imu.py        Imu: an IMU on the bus (gyro + accelerometer), values in SI units
    feedback.py   Feedback (snapshot of all motors), Rate (fixed loop rate)
    plotting.py   Recorder (record, plot afterwards), LivePlot (live window)
    registers.py  the memory table inside the motor
    units.py      raw numbers <-> SI units
    errors.py     what can go wrong
    ports/        sending bytes: to real motors, simulated ones, or over the network
    robots/       robot models for the simulation (MuJoCo)
"""

from servolab.bus import Bus
from servolab.errors import (
    CommunicationError,
    DuplicateIdError,
    NoResponseError,
    PortError,
    RegisterError,
    ServoLabError,
)
from servolab.feedback import Feedback, Rate
from servolab.imu import Imu, ImuFeedback
from servolab.motor import Motor
from servolab.plotting import LivePlot, Recorder
from servolab.ports.feetech_port import FeetechPort, find_adapter, list_ports
from servolab.ports.network_port import NetworkPort
from servolab.ports.sim_port import SimPort

__version__ = "1.0.0"

# What "from servolab import *" gives you, and what the documentation lists.
__all__ = [
    "connect", "list_ports", "find_adapter",
    "Bus", "Motor", "Imu", "ImuFeedback", "Feedback", "Rate", "Recorder", "LivePlot",
    "FeetechPort", "SimPort", "NetworkPort",
    "ServoLabError", "PortError", "NoResponseError", "CommunicationError", "RegisterError",
    "DuplicateIdError",
]

# Buses that are open right now, by port name. If you run your script twice
# in the same console, connect() gives you the existing bus instead of
# failing because the port is still open.
open_buses = {}


def connect(port=None, scan=True, sim_motor_ids=(1, 2, 3), show=True):
    """Open a bus and (normally) find all motors on it.

    port:          None   -> find the Waveshare adapter automatically
                   "COM5" -> this serial port (Windows), "/dev/ttyACM0" (Linux),
                             "/dev/cu.usbmodem..." (macOS)
                   "sim"  -> simulated motors, no hardware needed
                   "sim:so102" -> a simulated robot (needs: pip install "servolab[sim]")
                   "tcp://emr-mobile-3.local" -> motors on another computer, e.g. the
                             Raspberry Pi of a mobile robot (it runs servolab-server)
    scan:          False  -> don't look for motors (use bus.scan() later)
    sim_motor_ids: IDs of the simulated motors (only for port="sim")
    show:          False  -> no 3D window (only for simulated robots)

    Returns a Bus. Examples:
        bus = servolab.connect()                        # USB adapter, found automatically
        bus = servolab.connect("sim")                   # three simulated motors
        bus = servolab.connect("sim:so102")             # the simulated SO102 arm
        bus = servolab.connect("tcp://192.168.4.1")     # a robot over WiFi (in its WiFi network)
        print(bus.motors)
    """
    if port is None:
        port = find_adapter()

    existing = open_buses.get(port)
    if existing is not None and existing.connected:
        print(f"Already connected to {port}, using the existing connection.")
        return existing

    if port == "sim":
        bus = Bus(SimPort(sim_motor_ids))
    elif port.startswith("sim:"):
        from servolab.ports.mujoco_port import MujocoPort   # needs MuJoCo, so only loaded here
        bus = Bus(MujocoPort(port[len("sim:"):], show=show))
    elif port.startswith("tcp://"):
        bus = Bus(NetworkPort(port[len("tcp://"):]))
    else:
        bus = Bus(FeetechPort(port))

    if scan:
        try:
            bus.scan()
        except ServoLabError:
            bus.disconnect()      # free the port, so that connect() works again after the fix
            raise
        found = ", ".join(f"{motor_id} ({motor.model})" for motor_id, motor in bus.motors.items())
        message = f"Connected to {port}. Motors found: {found or 'none'}"
        if bus.sensors:
            sensors = ", ".join(f"{sensor_id} ({sensor.model})" for sensor_id, sensor in bus.sensors.items())
            message += f". Sensors found: {sensors}"
        print(message)

    open_buses[port] = bus
    return bus
