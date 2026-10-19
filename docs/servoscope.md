# ServoScope

A web app to look at and play with your motors and IMUs. It needs the `scope`
extra (`pip install "servolab[scope]"`, included in `servolab[all]`).

```bash
servoscope                      # opens in your browser (in a uv project: uv run servoscope)
servoscope --sim                # start connected to simulated motors
servoscope --sim so102          # start connected to the simulated SO102 arm
servoscope --connect /dev/ttyACM0               # connect to this port right away
servoscope --connect tcp://emr-mobile-3.local   # the motors of a robot, over WiFi
```

## What you can do

- **Connect** in the sidebar: choose the adapter's port, the simulator, or type
  the address of a robot (`tcp://...`). The sidebar lists all motors and
  sensors with a live value and a status dot.
- **Control** a motor: torque on/off, mode, a slider for the goal position,
  velocity or PWM, and "Set current position as zero".
- **Monitor**: live plot of position, velocity, current or load (5, 10 or
  30 s), with pause and CSV download.
- **PID tuning**: change the gains of the controller inside the motor and
  compare them with step tests.
- **Settings**: every register of the device with its description and unit,
  "Save to EEPROM" and "Factory reset".
- **IMUs**: live acceleration and angular velocity, plot, settings.
- **Documentation**: the guides, the Python API, the register tables and the
  examples of this website, without internet.
- **All torque off**: the red button at the bottom of the sidebar switches
  every motor off.

## Good to know

- Only one program can use the USB port at a time. Press **Disconnect** in
  ServoScope before running your own script, and connect again afterwards.
- ServoScope is only reachable from your own computer. `--host 0.0.0.0` opens
  it to the network: then everybody in the same network can move your motors.
- Changes in Settings are active immediately but lost after power-off, unless
  you press **Save to EEPROM**.

All options:

```text
servoscope [--sim [ROBOT]] [--connect PORT] [--port 8050] [--host 127.0.0.1] [--no-browser]
```

`--port` is the port of the web server (the address in your browser), not the
serial port.
