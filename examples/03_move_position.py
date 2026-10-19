"""
03 - Position mode: tell the motor where to go.
"""

import math

import servolab

PORT = None      # or "sim"

bus = servolab.connect(PORT)
m = bus[1]                       # the motor with ID 1

m.mode = "position"
m.torque_enabled = True          # now the motor holds its position

# The simple way: set the goal, the motor moves as fast as it can.
m.position = 0.0

# With limits, and wait until the motor has arrived:
m.move_to(math.pi / 2, speed=1.0, wait=True)    # 90 degrees at 1 rad/s
print("arrived at", m.position)

m.move_to(-math.pi / 2, speed=3.0, acceleration=10.0, wait=True)
print("arrived at", m.position)

m.torque_enabled = False
