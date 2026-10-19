"""
08 - Read an IMU (gyro + accelerometer) on the bus.

Needs an IMU on the bus (the XIAO IMU has ID 100 when it is new).
Tilt and turn it while this runs. Then try LIVE = True to see the values
as plots.
"""

import numpy as np

import servolab

PORT = None      # the IMU's own USB port works too, e.g. "/dev/cu.usbmodem..."
IMU_ID = 100
LIVE = False     # True = live plot window (Rerun viewer)

bus = servolab.connect(PORT)
imu = bus[IMU_ID]                # the IMU with ID 100 (an ID, not a list index!)
print(imu.info)                  # model, firmware, ranges, sample rate

rec = servolab.LivePlot() if LIVE else None

rate = servolab.Rate(50)         # 50 times per second
for _ in range(500):             # 10 seconds
    fb = imu.read()              # everything from the same moment, ONE message
    a_x, a_y, a_z = fb.acceleration          # m/s^2, includes gravity
    w_x, w_y, w_z = fb.angular_velocity      # rad/s

    if rec is not None:
        rec.add(time=fb.time, a_x=a_x, a_y=a_y, a_z=a_z, w_x=w_x, w_y=w_y, w_z=w_z)
    else:
        print(f"acc {a_x:+6.2f} {a_y:+6.2f} {a_z:+6.2f} m/s^2  (|a| = {np.linalg.norm(fb.acceleration):5.2f})   "
              f"gyro {w_x:+6.2f} {w_y:+6.2f} {w_z:+6.2f} rad/s")
    rate.sleep()

# Motors and IMUs in one go: bus.read_feedback() also reads all sensors.
fb = bus.read_feedback()
print("motors:", fb.ids, " IMU acceleration:", fb.sensors[IMU_ID].acceleration)
