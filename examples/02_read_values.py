"""
02 - Read values from one motor.

Turn the motor by hand while this runs: torque is off, so it turns freely.
"""

import time

import servolab

PORT = None      # or "sim"

bus = servolab.connect(PORT)
m = bus[1]                       # the motor with ID 1 (an ID, not a list index!)

print(m.info)                    # overview: model, firmware, mode, ...

m.torque_enabled = False         # motor is free, you can turn it by hand

for _ in range(50):
    print(f"position {m.position:+.2f} rad   "
          f"velocity {m.velocity:+.2f} rad/s   "
          f"current {m.current:.3f} A   "
          f"temperature {m.temperature} degC")
    time.sleep(0.1)
