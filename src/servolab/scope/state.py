"""
ServoScope state: the connection, a background poller and the recorded history.

There is exactly one ScopeState per ServoScope process (see `scope_state` at the
bottom). Every browser tab shows the same state.

Threading model:
- The poller thread reads feedback from all online motors and sensors (IMUs) at
  POLL_HZ and appends it to per-device ring buffers. It never touches UI elements.
- The UI (NiceGUI event loop) reads those buffers on a timer and calls servolab
  functions directly for user actions. The Bus lock serialises both.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

import servolab
from servolab.errors import NoResponseError, PortError, ServoLabError

POLL_HZ = 50                 # feedback rate of the poller
HISTORY_SECONDS = 30         # how much history the plots and CSV export keep
OFFLINE_RETRY_SECONDS = 2.0  # how often to ping motors that stopped answering
SIM_PORT = "sim"


@dataclass
class MotorHistory:
    """Ring buffers with the recent feedback of one motor."""

    maxlen: int = POLL_HZ * HISTORY_SECONDS
    t: deque = field(default_factory=deque)
    position: deque = field(default_factory=deque)
    velocity: deque = field(default_factory=deque)
    current: deque = field(default_factory=deque)
    load: deque = field(default_factory=deque)
    goal: deque = field(default_factory=deque)   # last position goal sent from the UI (or None)

    def __post_init__(self):
        """Give every buffer its maximum length (a plain deque would grow forever)."""
        for name in ("t", "position", "velocity", "current", "load", "goal"):
            setattr(self, name, deque(maxlen=self.maxlen))

    def clear(self):
        """Forget all recorded values."""
        for buffer in (self.t, self.position, self.velocity, self.current, self.load, self.goal):
            buffer.clear()


@dataclass
class MotorLive:
    """Latest values of one motor (for the sidebar and the info section)."""

    position: float = 0.0
    velocity: float = 0.0
    current: float = 0.0
    load: float = 0.0
    voltage: float = 0.0
    temperature: float = 0.0
    status: list = field(default_factory=list)
    online: bool = True


@dataclass
class SensorHistory:
    """Ring buffers with the recent measurements of one IMU (vectors as [x, y, z])."""

    maxlen: int = POLL_HZ * HISTORY_SECONDS
    t: deque = field(default_factory=deque)
    acceleration: deque = field(default_factory=deque)
    angular_velocity: deque = field(default_factory=deque)

    def __post_init__(self):
        """Give every buffer its maximum length (a plain deque would grow forever)."""
        for name in ("t", "acceleration", "angular_velocity"):
            setattr(self, name, deque(maxlen=self.maxlen))

    def clear(self):
        """Forget all recorded values."""
        for buffer in (self.t, self.acceleration, self.angular_velocity):
            buffer.clear()


@dataclass
class SensorLive:
    """Latest values of one IMU."""

    acceleration: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    angular_velocity: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    online: bool = True


class ScopeState:
    """Everything ServoScope knows: the bus, the selected device, live values and history."""
    def __init__(self):
        self.bus: servolab.Bus | None = None
        self.port_name: str | None = None
        self.connection: str = "disconnected"   # disconnected | connecting | connected | lost
        self.connection_message: str = ""

        self.selected_id: int | None = None
        self.view: str = "motor"                 # motor | sensor | docs

        self.live: dict[int, MotorLive] = {}
        self.history: dict[int, MotorHistory] = {}
        self.sensor_live: dict[int, SensorLive] = {}
        self.sensor_history: dict[int, SensorHistory] = {}
        self.goal: dict[int, float | None] = {}  # position goal set from the UI, for the plot
        self.paused = False                      # pause recording (plots freeze)
        self.loop_hz = 0.0                       # measured poll rate

        self._thread: threading.Thread | None = None
        self._running = False
        self._last_offline_check = 0.0

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, port_name: str) -> None:
        """Blocking: open the bus and scan. Run via nicegui.run.io_bound."""
        self.disconnect()
        self.connection = "connecting"
        self.connection_message = f"Connecting to {port_name} ..."
        bus = None
        try:
            if port_name == SIM_PORT:
                bus = servolab.Bus(servolab.SimPort((1, 2, 3)))
            elif port_name.startswith("sim:"):
                from servolab.ports.mujoco_port import MujocoPort
                bus = servolab.Bus(MujocoPort(port_name[len("sim:"):], show=True))
            elif port_name.startswith("tcp://"):
                bus = servolab.Bus(servolab.NetworkPort(port_name[len("tcp://"):]))
            else:
                bus = servolab.Bus(servolab.FeetechPort(port_name))
            bus.scan()
        except ServoLabError as error:
            if bus is not None:
                bus.disconnect()       # free the port again (e.g. after a duplicate ID error)
            self.connection = "disconnected"
            self.connection_message = str(error)
            raise

        self.bus = bus
        self.port_name = port_name
        self.connection = "connected"
        self.connection_message = ""
        self._reset_motor_data()
        self._start_polling()

    def rescan(self) -> None:
        """Blocking: look for motors again (e.g. after changing an ID)."""
        if self.bus is None:
            return
        self.bus.scan()
        self._reset_motor_data()

    def disconnect(self) -> None:
        """Switch torque off, stop polling, close the port."""
        self._stop_polling()
        if self.bus is not None:
            self.bus.disconnect()
        self.bus = None
        self.port_name = None
        self.connection = "disconnected"
        self.connection_message = ""
        self.live.clear()
        self.history.clear()
        self.sensor_live.clear()
        self.sensor_history.clear()
        self.goal.clear()
        self.selected_id = None

    @property
    def motor_ids(self) -> list[int]:
        """IDs of all motors found, sorted (empty while disconnected)."""
        return sorted(self.bus.motors) if self.bus else []

    @property
    def sensor_ids(self) -> list[int]:
        """IDs of all sensors (IMUs) found, sorted."""
        return sorted(self.bus.sensors) if self.bus else []

    @property
    def device_ids(self) -> list[int]:
        """Motors first, then sensors: the order of the device list in the sidebar."""
        return self.motor_ids + self.sensor_ids

    def motor(self, motor_id: int | None = None) -> servolab.Motor | None:
        """The selected motor, or the one with `motor_id`. None if there is no such motor."""
        motor_id = self.selected_id if motor_id is None else motor_id
        if self.bus is None or motor_id not in self.bus.motors:
            return None
        return self.bus.motors[motor_id]

    def sensor(self, sensor_id: int | None = None) -> servolab.Imu | None:
        """The selected IMU, or the one with `sensor_id`. None if there is no such IMU."""
        sensor_id = self.selected_id if sensor_id is None else sensor_id
        if self.bus is None or sensor_id not in self.bus.sensors:
            return None
        return self.bus.sensors[sensor_id]

    def _reset_motor_data(self) -> None:
        """Fresh live values and empty histories for every device the bus has found."""
        self.live = {motor_id: MotorLive() for motor_id in self.motor_ids}
        self.history = {motor_id: MotorHistory() for motor_id in self.motor_ids}
        self.goal = {motor_id: None for motor_id in self.motor_ids}
        self.sensor_live = {sensor_id: SensorLive() for sensor_id in self.sensor_ids}
        self.sensor_history = {sensor_id: SensorHistory() for sensor_id in self.sensor_ids}
        if self.selected_id not in self.device_ids:
            self.selected_id = self.device_ids[0] if self.device_ids else None
        if self.view != "docs":
            self.view = "sensor" if self.selected_id in self.sensor_live else "motor"

    # ------------------------------------------------------------------
    # Poller
    # ------------------------------------------------------------------

    def _start_polling(self) -> None:
        """Start the poller thread."""
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, name="servoscope-poller", daemon=True)
        self._thread.start()

    def _stop_polling(self) -> None:
        """Stop the poller thread and wait for it (unless the poller itself calls this)."""
        self._running = False
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _poll_loop(self) -> None:
        """Poller thread: read feedback at POLL_HZ until stopped or the connection is lost."""
        rate = servolab.Rate(POLL_HZ)
        last = time.perf_counter()
        while self._running:
            bus = self.bus
            if bus is None:
                break
            try:
                self._poll_once(bus)
            except PortError as error:
                self._connection_lost(str(error))
                break
            except ServoLabError:
                pass  # transient bus error: try again next cycle
            now = time.perf_counter()
            self.loop_hz = 0.9 * self.loop_hz + 0.1 * (1.0 / max(now - last, 1e-6))
            last = now
            rate.sleep()

    def _poll_once(self, bus: servolab.Bus) -> None:
        """Read the feedback of all online devices once. A device that does not answer goes offline."""
        online = [motor_id for motor_id, live in self.live.items() if live.online]
        online += [sensor_id for sensor_id, live in self.sensor_live.items() if live.online]
        if online:
            try:
                fb = bus.read_feedback(online)
            except NoResponseError as error:
                for device_id in error.motor_ids:
                    live = self.live.get(device_id) or self.sensor_live.get(device_id)
                    if live is not None:
                        live.online = False
                return
            self._store(fb)
            self._store_sensors(fb)
        self._retry_offline(bus)

    def _store(self, fb: servolab.Feedback) -> None:
        """Copy motor feedback into the live values and, unless paused, into the history."""
        for i, motor_id in enumerate(fb.ids):
            live = self.live.get(motor_id)
            if live is None:
                continue
            live.position = float(fb.position[i])
            live.velocity = float(fb.velocity[i])
            live.current = float(fb.current[i])
            live.load = float(fb.load[i])
            live.voltage = float(fb.voltage[i])
            live.temperature = float(fb.temperature[i])
            live.status = fb.status[i]
            if self.paused:
                continue
            history = self.history[motor_id]
            history.t.append(fb.time)
            history.position.append(live.position)
            history.velocity.append(live.velocity)
            history.current.append(live.current)
            history.load.append(live.load)
            history.goal.append(self.goal.get(motor_id))

    def _store_sensors(self, fb: servolab.Feedback) -> None:
        """Copy IMU measurements into the live values and, unless paused, into the history."""
        for sensor_id, imu in fb.sensors.items():
            live = self.sensor_live.get(sensor_id)
            if live is None:
                continue
            live.acceleration = [float(v) for v in imu.acceleration]
            live.angular_velocity = [float(v) for v in imu.angular_velocity]
            if self.paused:
                continue
            history = self.sensor_history[sensor_id]
            history.t.append(imu.time)
            history.acceleration.append(live.acceleration)
            history.angular_velocity.append(live.angular_velocity)

    def _retry_offline(self, bus: servolab.Bus) -> None:
        """Every OFFLINE_RETRY_SECONDS, ping the offline devices to see whether they are back."""
        now = time.perf_counter()
        if now - self._last_offline_check < OFFLINE_RETRY_SECONDS:
            return
        self._last_offline_check = now
        for motor_id, live in list(self.live.items()) + list(self.sensor_live.items()):
            if not live.online:
                with bus.lock:
                    answered = bus.port.ping(motor_id, timeout_ms=10) is not None
                live.online = answered

    def _connection_lost(self, message: str) -> None:
        """The port is gone (e.g. cable unplugged): drop the bus and tell the UI why."""
        self._running = False
        bus = self.bus
        self.bus = None
        if bus is not None:
            bus.disconnect()
        self.connection = "lost"
        self.connection_message = message


scope_state = ScopeState()
