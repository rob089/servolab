# Simulation

servolab has two kinds of simulation. Both work like real hardware: the same
registers, the same functions, the same errors. Your program does not change,
only the port.

## Simulated motors: `connect("sim")`

```python
bus = servolab.connect("sim")                         # three motors, IDs 1, 2, 3
bus = servolab.connect("sim", sim_motor_ids=(1, 5))   # or the IDs you want
```

Each motor is a memory table plus a very simple physics model: no load, no
gravity. Good for trying out code at home, for tests and for ServoScope
without hardware. Don't tune controllers on it: the numbers are plausible,
not accurate. `connect("sim", sim_motor_ids=(1, 1))` shows what happens when
two motors have the same ID.

## Simulated robots: `connect("sim:so102")`

With MuJoCo installed (`pip install "servolab[sim]"`) servolab simulates a
whole robot: parts with their real masses, gravity, the floor, and every
joint driven by a simulated STS3215 (its position, velocity and PWM modes, and
a DC motor model that gets weaker the faster it turns).

```python
bus = servolab.connect("sim:so102")      # the SO102 arm, servo IDs 1-7, with a 3D view
bus = servolab.connect("sim:so102", show=False)   # without the 3D view (faster, for tests)
```

The simulation runs in real time, also while your program sleeps. The 3D
view is the Rerun viewer, the same window as `servolab.LivePlot`.

A simulated robot can do a few things a real one can't:

```python
bus.sim.tcp()                      # true pose of the gripper (4x4 matrix, base frame, m)
bus.sim.pose("wrist")              # true pose of any body or site of the model
bus.sim.mark("my_tcp", T)          # show a point in the 3D view, e.g. your own kinematics
bus.sim.mark_frame("goal", T)      # show a coordinate frame (x red, y green, z blue)
```

`bus.sim` is `None` for real hardware, so you can check `if bus.sim:`.

The motor and controller numbers in the simulation are estimates. The
simulated robot behaves plausibly, not exactly like the real one.

## Your own robot

Any MuJoCo model (MJCF, `.xml`) works if it follows three rules:

1. Every joint driven by a servo is a hinge joint with a `<motor>` of the
   **same name**.
2. The `ctrlrange` of that `<motor>` is the stall torque of the servo in N m
   (e.g. `ctrlrange="-2.9 2.9"`).
3. The servo ID of each joint is written in the model:

```xml
<custom>
  <numeric name="servo_id:shoulder" data="1"/>
  <numeric name="servo_id:elbow" data="2"/>
</custom>
```

Then connect with the path of the file:

```python
bus = servolab.connect("sim:/path/to/my_robot.xml")
```

or put it into the package as `servolab/robots/<name>/scene.xml` and use
`connect("sim:<name>")`; ServoScope then lists it too. A mobile robot works
the same way: give its body a `<freejoint/>` and drive its wheels in velocity
mode. `src/servolab/robots/so102/` is a complete example.

Good to know:

- The 3D view only draws **mesh** geoms (STL files) in geom group 2, like
  the visual parts of the SO102. Parts made of simple shapes (boxes,
  cylinders) and the floor are simulated, but not drawn.
- There is no simulated IMU: `bus.sensors` stays empty.
- Every servo is simulated as an STS3215 at 7.4 V.
