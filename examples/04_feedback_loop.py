"""
04 - Read all motors in a loop at a fixed rate, and plot the result.

read_feedback() reads every motor with ONE message on the bus, which is
much faster than asking each motor separately.
"""

import matplotlib.pyplot as plt
import numpy as np

import servolab

PORT = None      # or "sim"

bus = servolab.connect(PORT)
bus.torque_off_all()             # turn the motors by hand while recording

rate = servolab.Rate(100)        # 100 Hz
times = []
positions = []

for _ in range(300):             # 300 passes at 100 Hz = 3 seconds
    fb = bus.read_feedback()
    times.append(fb.time)
    positions.append(fb.position)
    rate.sleep()

positions = np.array(positions)  # rows = time steps, columns = motors (see fb.ids)

for column, motor_id in enumerate(fb.ids):
    plt.plot(times, positions[:, column], label=f"motor {motor_id}")
plt.xlabel("time [s]")
plt.ylabel("position [rad]")
plt.legend()
plt.show()
