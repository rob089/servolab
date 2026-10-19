"""
01 - Connect and find all motors.

Set PORT = "sim" to try this without hardware.
"""

import servolab

PORT = None      # None = find the Waveshare adapter automatically, or "sim"

# Which serial ports does this computer have?
print(servolab.list_ports())

# Open the bus and scan every ID (0...252) whether a motor is there.
bus = servolab.connect(PORT)

print(bus)
for motor_id, motor in bus.motors.items():
    print(f"ID {motor_id}: {motor.model}")
