"""
feedback.py - a snapshot of all motors at one moment, and loops at a fixed rate.

    fb = bus.read_feedback()
    fb.position          # array with the position of every motor, in rad
    fb.of(1)             # everything about motor 1, as a dict
    fb.sensors[100]      # the IMU with ID 100 (an ImuFeedback, see imu.py)

The arrays are sorted like fb.ids. So if fb.ids is [1, 2, 5], then
fb.position[0] belongs to motor 1, fb.position[2] belongs to motor 5.
(Remember: Python starts counting at 0.)

For control loops that should run at a fixed rate, use Rate:

    rate = servolab.Rate(100)      # 100 times per second
    while True:
        fb = bus.read_feedback()
        ...                        # your controller
        rate.sleep()               # waits for the rest of the 10 ms
"""

import time
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Feedback:
    """State of all motors (and sensors), read in one go."""

    time: float                # seconds since connect()
    ids: list                  # motor IDs, in the same order as the arrays below
    position: np.ndarray       # rad
    velocity: np.ndarray       # rad/s
    current: np.ndarray        # A
    load: np.ndarray           # -1.0 ... 1.0 (1.0 = 100 %)
    voltage: np.ndarray        # V
    temperature: np.ndarray    # degrees Celsius
    status: list               # list of problems per motor, e.g. [[], ['overheat'], []]
    sensors: dict = field(default_factory=dict)   # sensor ID -> ImuFeedback (see imu.py)

    def of(self, motor_id):
        """All values of one motor (or sensor) as a dict. Example: fb.of(1)['position']"""
        if motor_id in self.sensors:
            imu = self.sensors[motor_id]
            return {
                "acceleration": imu.acceleration,
                "angular_velocity": imu.angular_velocity,
                "quaternion": imu.quaternion,
            }
        i = self.ids.index(motor_id)
        return {
            "position": self.position[i],
            "velocity": self.velocity[i],
            "current": self.current[i],
            "load": self.load[i],
            "voltage": self.voltage[i],
            "temperature": self.temperature[i],
            "status": self.status[i],
        }


class Rate:
    """Helps a loop run at a fixed rate (like a metronome).

    rate = Rate(100) and rate.sleep() at the end of each loop pass make the
    loop run 100 times per second, as long as one pass takes less than 10 ms.
    If a pass takes longer, sleep() does not wait at all and the rate drops.
    """

    def __init__(self, hz):
        self.period = 1.0 / hz
        self.next_time = time.perf_counter() + self.period

    def sleep(self):
        """Wait until the next period starts. Call it once at the end of every loop pass."""
        wait = self.next_time - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
            self.next_time += self.period
        else:
            # We are late. Don't try to catch up, just start a new period from now.
            self.next_time = time.perf_counter() + self.period
