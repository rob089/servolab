# servolab

[![tests](https://github.com/rob089/servolab/actions/workflows/tests.yml/badge.svg)](https://github.com/rob089/servolab/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/servolab)](https://pypi.org/project/servolab/)
[![docs](https://img.shields.io/badge/docs-rob089.github.io%2Fservolab-3070b3)](https://rob089.github.io/servolab/)

Control Feetech serial bus servos (STS3215 and friends) from Python.
Made for teaching robotics: readable code, SI units, a simulator and a web app
to look at your motors. Developed for the robotics seminar of the TUM Chair of
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

No hardware? `servolab.connect("sim")` gives you simulated motors, and
`servolab.connect("sim:so102")` a whole simulated robot arm.

**Documentation: [rob089.github.io/servolab](https://rob089.github.io/servolab/)**:
guides, the Python API, the register tables and the examples.

## Installation

```bash
pip install "servolab[all]"
```

or, in a [uv](https://docs.astral.sh/uv/) project: `uv add "servolab[all]"`.
Python 3.10 or newer, on Windows, macOS and Linux.

The core (motors, IMU, simulated motors, network) only needs numpy and pyserial.
Everything else is optional:

| Extra          | Adds                                   | Packages                  |
|----------------|----------------------------------------|---------------------------|
| `scope`        | the ServoScope web app                 | nicegui                   |
| `plot`         | `rec.plot()`, `LivePlot`               | matplotlib, rerun-sdk     |
| `kinematics`   | the robotics toolbox (used in courses) | roboticstoolbox-python    |
| `sim`          | simulated robots with physics          | mujoco, rerun-sdk         |
| `all`          | everything above                       |                           |

## What's inside

- **Motors** (`bus[1]`): position, velocity and PWM mode, all values in SI units,
  several motors at once with one message (`bus.read_feedback()`, `bus.move_to()`).
- **IMUs on the bus**: a gyro + accelerometer that sits on the servo cable like
  one more motor ([firmware](https://github.com/rob089/servolab/tree/main/firmware/xiao_imu) for a Seeed XIAO nRF52840 Sense).
- **Recording and plotting**: `servolab.Recorder()` and a live plot window (`servolab.LivePlot()`).
- **Simulation**: simulated motors without any extra package, and whole robots in
  MuJoCo with a 3D view (`connect("sim:so102")`, or your own robot model).
- **Robots over WiFi**: `servolab-server` on the robot, `connect("tcp://robot.local")`
  on the laptop; the motors switch off when the connection breaks.
- **ServoScope**: a web app with live plots, sliders, PID step tests, every register
  and the documentation:

```bash
servoscope                  # opens in your browser (in a uv project: uv run servoscope)
servoscope --sim            # try it with simulated motors
```

## Learning path

The [`examples/`](https://github.com/rob089/servolab/tree/main/examples) folder goes step by step:

1. `01_connect_and_scan.py` - connect, list motors
2. `02_read_values.py` - read position, current, temperature ...
3. `03_move_position.py` - position mode
4. `04_feedback_loop.py` - read all motors in a loop at a fixed rate
5. `05_pwm_mode.py` - drive the motor voltage directly
6. `06_registers.py` - read and write any register
7. `07_plotting.py` - record values, plot them afterwards or live
8. `08_imu.py` - read an IMU on the bus

## Development

```bash
git clone https://github.com/rob089/servolab
cd servolab
uv sync --all-extras           # installs Python, servolab (editable) and all extras
uv run pytest                  # all tests run without hardware
```

The library code (everything outside `scope/`) is meant to be read by students
with little Python experience: plain loops, explicit properties, units in the
docstrings, the Feetech SDK used in exactly one file. Please keep it that way.
More in the [development guide](https://rob089.github.io/servolab/development/).

## License

MIT, see [LICENSE](https://github.com/rob089/servolab/blob/main/LICENSE). The bundled Feetech SDK (`src/servolab/_sdk/`) is
MIT-licensed by ftservo.
