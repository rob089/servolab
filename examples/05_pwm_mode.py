"""
05 - PWM mode: you decide how much voltage the motor gets.

In PWM mode there is no controller inside the motor. m.pwm = 0.3 means
"30 % of the supply voltage". This is the starting point for writing your
own controller (for example a PID controller).

Careful: the motor does not stop by itself. Keep your hand off the shaft.
"""

import time

import servolab

PORT = None      # or "sim"

bus = servolab.connect(PORT)
m = bus[1]                       # the motor with ID 1

m.mode = "pwm"
m.torque_enabled = True

m.pwm = 0.2                      # slowly one way
time.sleep(1.0)
print("velocity at 20 % PWM:", m.velocity, "rad/s")

m.pwm = -0.4                     # faster the other way
time.sleep(1.0)
print("velocity at -40 % PWM:", m.velocity, "rad/s")

m.pwm = 0.0
m.torque_enabled = False
m.mode = "position"              # back to the normal mode
