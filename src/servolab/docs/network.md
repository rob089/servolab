# Robots over WiFi

A mobile robot has its own small computer, e.g. a Raspberry Pi, with the USB
adapter and the motors. Your program runs on your laptop and talks to the
motors over WiFi. On the robot, `servolab-server` passes everything on to the
motors.

```python
import servolab

bus = servolab.connect("tcp://emr-mobile-3.local")   # name or address of the robot
bus.motors                                           # as with a USB cable
fb = bus.read_feedback()
```

In ServoScope, type the address into the port field: `tcp://emr-mobile-3.local`.

## Good to know

- **Your laptop must be in the robot's WiFi.** Then it usually has no internet.
- **Only one program at a time** can use the motors. A second one gets the
  error *"The motors are already used by ..."*. Disconnect in ServoScope (or
  end your other program) first.
- **Safety:** if the WiFi breaks or your program hangs for more than 1 s, the
  robot switches all motors off. Your program then gets the error
  *"Lost the connection ..."*. Connect again.
- **Timing:** each message takes a few milliseconds over WiFi, sometimes much
  longer. Control loops up to about 50 Hz work well; for faster loops use a
  USB cable.
- **Camera, LEDs, ...** of the robot are not part of servolab. Your exercise
  sheet tells you how to use them.
