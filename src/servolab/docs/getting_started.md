# Getting started

servolab lets you control Feetech serial bus servos (like the STS3215) from Python.
ServoScope, the web app that comes with servolab, is built on top of it: everything
you can click there, you can also do in your own code.

## Your first lines of code

```python
import servolab

bus = servolab.connect()      # find the USB adapter and all motors on the cable
print(bus.motors)             # {1: <Motor 1: STS3215>, ...}

m = bus[1]                    # the motor with ID 1 (an ID, not a list index!)
print(m.position)             # where is it? in rad
```

No hardware at hand? `servolab.connect("sim")` gives you three simulated motors.
`servolab.connect("sim:so102")` simulates the whole SO102 arm (with gravity and a
3D view) - this needs MuJoCo: `pip install "servolab[sim]"`. See the
**Simulation** guide.

## Moving a motor

```python
m.mode = "position"           # the motor goes to a goal and holds it
m.torque_enabled = True       # power on – the motor now holds its position
m.position = 0.5              # go to 0.5 rad

m.move_to(1.0, speed=2.0, wait=True)   # slower, and wait until it arrived
m.torque_enabled = False      # power off – you can turn it by hand again
```

## Moving several motors at once

The bus has the same two ways, for several motors with ONE message:

```python
bus.write_positions([0.5, -0.5])                  # like m.position = ..., sorted like fb.ids
bus.move_to([0.5, -0.5], speed=1.0, wait=True)    # like m.move_to(...)
bus.move_to({1: 0.5, 3: 0.0})                     # or {motor_id: rad}
```

`bus.move_to()` starts all motors together, but each one moves at `speed`:
a motor with a shorter way arrives earlier.

## Reading all motors in a loop

```python
rate = servolab.Rate(100)     # 100 times per second
while True:
    fb = bus.read_feedback()  # all motors with ONE message on the bus
    print(fb.position)        # numpy array, sorted like fb.ids
    rate.sleep()
```

## Plotting your measurements

```python
rec = servolab.Recorder()     # or servolab.LivePlot() to watch live
for _ in range(300):
    fb = bus.read_feedback()
    rec.add(time=fb.time, position=fb.of(1)["position"])
    rate.sleep()
rec.plot()                    # after the loop: position over time
```

Don't draw with matplotlib inside your loop: drawing is slow and changes how
your controller behaves.

## IMUs on the bus

An IMU on the cable shows up in `bus.sensors` and works like a motor:
`imu = bus[100]`, then `imu.read().acceleration`. `bus.read_feedback()` reads
motors and IMUs together. See the **IMU** guide.

## ServoScope and your code

Only one program can use the USB port at a time. Before you run your own script,
press **Disconnect** in ServoScope (and connect again afterwards).

## Where to look things up

- **Python API**: every function and property, with units.
- **Registers**: the memory table inside the motor.
- **Examples**: small programs to start from.

In ServoScope these are the tabs of the documentation page; `help(m.move_to)`
in Python shows the same text.
