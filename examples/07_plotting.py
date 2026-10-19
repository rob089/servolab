"""
07 - Record values in a loop and plot them.

Motor 1 follows a slow sine wave for 10 seconds. Its position and the goal are
recorded and plotted afterwards. With LIVE = True you also watch them live
while the loop runs; with LIVE = False they are only recorded.
"""

import math

import servolab

PORT = None      # or "sim"
LIVE = True      # True = open a live plot window (Rerun viewer)

bus = servolab.connect(PORT)
m = bus[1]                       # the motor with ID 1
m.mode = "position"
m.torque_enabled = True

if LIVE:
    rec = servolab.LivePlot()    # records AND shows live
else:
    rec = servolab.Recorder()    # only records

rate = servolab.Rate(100)        # 100 Hz
for step in range(1000):         # 1000 passes at 100 Hz = 10 seconds
    goal = math.sin(step / 1000 * 2 * math.pi)     # one full sine period, -1 ... 1 rad
    m.move_to(goal, speed=2.0, acceleration=10.0)

    fb = bus.read_feedback()
    rec.add(time=fb.time, position=fb.of(1)["position"], goal=goal)
    rate.sleep()

m.torque_enabled = False

rec.plot()                       # position and goal over time
rec.save("07_recording.csv")     # open it in Excel, or load it with numpy
