# Development

```bash
git clone https://github.com/rob089/servolab
cd servolab
uv sync --all-extras           # installs Python, servolab (editable) and all extras
uv run pytest                  # all tests run without hardware
uv run servoscope --sim        # try ServoScope with simulated motors
```

The library code (everything outside `scope/`) is meant to be read by students
with little Python experience: plain loops, explicit properties, units in the
docstrings, the Feetech SDK used in exactly one file. Please keep it that way.

## How the code is organised

```text
src/servolab/
  __init__.py      connect(), list_ports()        <- start reading here
  bus.py           Bus: all motors on one cable
  motor.py         Motor: one motor, values in SI units
  imu.py           Imu: an IMU on the bus (gyro + accelerometer), values in SI units
  feedback.py      Feedback (snapshot of all motors), Rate (fixed loop rate)
  plotting.py      Recorder (record, plot afterwards), LivePlot (live window)
  registers.py     the memory table inside the motor
  units.py         raw numbers <-> SI units
  errors.py        what can go wrong
  server.py        servolab-server: share the motors over the network
  ports/
    feetech_port.py   real motors (the only file using the Feetech SDK)
    sim_port.py       simulated motors
    network_port.py   motors on another computer (servolab-server)
    mujoco_port.py    a simulated robot (MuJoCo physics + servo firmware model)
  robots/so102/    MuJoCo model of the SO102 arm (MJCF + meshes)
  docs/            the guides (shown in ServoScope and on this website)
  scope/           ServoScope, the web app (NiceGUI)
  _sdk/            bundled Feetech SDK (internal, don't import)
firmware/xiao_imu/ firmware of the bus IMU (PlatformIO)
examples/          the example scripts
docs/              this website (MkDocs)
```

## This website

The guides live in `src/servolab/docs/`, so ServoScope can show them without
internet. The Python API, the register tables and the examples are generated
from the code by `docs/gen_pages.py`, using the same list of API entries as
ServoScope (`servolab/scope/reference.py`). To work on the website:

```bash
uv run --group docs mkdocs serve     # http://127.0.0.1:8000, reloads on every change
```

GitHub Actions builds the site on every push to `main` and publishes it on
GitHub Pages.

## Releasing a new version

1. Set the new version in `src/servolab/__init__.py` (`__version__`; the
   package version is read from there).
2. Move the entries under "Unreleased" in `CHANGELOG.md` to a new section
   with the version and the date.
3. Commit, then tag and push:

```bash
git tag v1.1.0
git push origin v1.1.0
```

The tag starts the `publish` workflow: it checks that the tag matches
`__version__`, builds the package and uploads it to PyPI.
