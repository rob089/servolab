# Troubleshooting

**"No Waveshare adapter found"**
Is the USB cable plugged in? On Windows, the adapter should appear as a COM port in
the Device Manager. If it doesn't, install the WCH CH343 driver.

**"Could not open COM5: is ServoScope or another program using it?"**
Only one program can use the port. Disconnect in ServoScope, or close the other
Python console that is still connected (`bus.disconnect()`).

**"Could not open /dev/ttyACM0: no permission"**
On Linux, serial ports belong to the `dialout` group:
`sudo usermod -aG dialout $USER`, then log out and in again.

**"Motor 3 does not answer"**
Check the power supply (7.4 V) and the 3-pin cables, and whether the motor really
has this ID (`bus.scan()`). If it happens only during fast moves, the supply is
too weak: the voltage drops, the motor restarts and is silent for a moment.

**"Garbled answer from motor 3"**
Electrical noise or a dip in the supply voltage. Check the cables and the power
supply.

**No motors found after connecting**
Is the power supply on? The USB cable alone does not power the motors.

**The motor does not move**
Is torque on? Is the motor in the right mode for your command?
Look at the status chip at the top of the motor page: "overload" or "overheat"
means the motor protected itself. Switch torque off, let it cool down, and try again.

**New motors all have ID 1**
Connect them one at a time and give each a new ID first
(ServoScope → Settings → Identity → `id`).

**"Several devices have ID 1"**
Two devices on the cable have the same ID, e.g. two new motors. `bus.scan()`
notices this and stops: every command would reach both of them, and their
answers collide. Switch the power off, plug in only one of them, give it its
own ID (`bus[1].id = 2`), then plug in the next one. If only one device has
this ID, its answers were garbled: check the cables and the power supply.
