# servolab

Control Feetech serial bus servos (STS3215 and friends) from Python. Made for
teaching robotics: readable code, SI units, a simulator and a web app to look
at your motors. Developed for the robotics seminar of the TUM Chair of
Microtechnology and Medical Device Technology (MiMed).

```python
import servolab

bus = servolab.connect()        # finds the Waveshare USB adapter and all motors
m = bus[1]                      # the motor with ID 1 (an ID, not a list index)

m.mode = "position"
m.torque_enabled = True
m.position = 0.5                # rad
print(m.position, m.current, m.temperature)
```

No hardware? `servolab.connect("sim")` gives you three simulated motors.

## Installation

```bash
pip install "servolab[all]"
```

or, in a [uv](https://docs.astral.sh/uv/) project:

```bash
uv add "servolab[all]"
```

Python 3.10 or newer, on Windows, macOS and Linux. The core (motors, IMU,
simulated motors, network) only needs numpy and pyserial; everything else is
optional:

| Extra        | Adds                                   | Packages                  |
|--------------|----------------------------------------|---------------------------|
| `scope`      | the [ServoScope](servoscope.md) web app | nicegui                  |
| `plot`       | `rec.plot()`, `LivePlot`               | matplotlib, rerun-sdk     |
| `kinematics` | the robotics toolbox (used in courses) | roboticstoolbox-python    |
| `sim`        | [simulated robots](guides/simulation.md) with physics | mujoco, rerun-sdk |
| `all`        | everything above                       |                           |

A computer that only [shares its motors over the network](guides/network.md),
e.g. the Raspberry Pi of a mobile robot, needs just `pip install servolab`.

## Where to go next

- **[Getting started](guides/getting_started.md)**: your first lines of code, moving
  motors, loops and plots.
- **[Examples](examples.md)**: small programs that go step by step.
- **[Python API](api.md)**: every function and property, with units.
- **[ServoScope](servoscope.md)**: look at your motors in the browser.
- **[Hardware](hardware.md)**: wiring, IDs, and what was checked on real motors.
