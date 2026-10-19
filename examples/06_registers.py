"""
06 - Registers: the memory table inside the motor.

Everything the properties (m.position, m.pid, ...) do is reading and writing
registers. You can also do that directly, by name. All names, addresses and
explanations are in src/servolab/registers.py.
"""

import servolab
from servolab.registers import STS3215_REGISTERS

PORT = None      # or "sim"

bus = servolab.connect(PORT)
m = bus[1]                       # the motor with ID 1

# Read every register and print it with its explanation
for register in STS3215_REGISTERS:
    value = m.read_register(register.name)
    print(f"{register.address:3d}  {register.name:30s} = {value:6d} {register.unit:14s} {register.description}")

# Raw values: present_position is in steps (4096 per turn, 2048 = middle)
print("raw position:", m.read_register("present_position"), "steps")

# Writing: change the dead zone of the internal controller.
# Without save=True the change is lost after power-off.
m.write_register("cw_dead_zone", 2)
m.write_register("ccw_dead_zone", 2)
