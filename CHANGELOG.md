# Changelog

## 1.0.0 (2026-10-20)

First release on PyPI, and the first version as its own repository (before,
servolab lived inside the course repository of the TUM MiMed robotics seminar).

- Bus, Motor and Imu classes with SI units; position, velocity and PWM mode
- `set_zero()` holds in every mode: the motor applies `homing_offset` only in
  position mode, servolab subtracts it in velocity and PWM mode
- `bus.scan()` finds two devices with the same ID and stops with a
  `DuplicateIdError` that names the ID (on the bus they look like one device,
  or like none)
- Factory reset for motors and IMUs (`m.factory_reset()`, `imu.factory_reset()`).
  Motors are reset with instruction 0x06 (the Feetech SDK's 0x0A is ignored by
  the STS3215); every device keeps its ID, so one motor in a chain can be reset
- Simulated motors (`connect("sim")`) and simulated robots in MuJoCo
  (`connect("sim:so102")`, or your own robot model)
- Recorder and LivePlot (Rerun) for recording and plotting
- Motors over the network: `servolab-server` on the robot, `connect("tcp://...")`
  on the laptop, with a watchdog that switches the motors off when the
  connection breaks
- ServoScope web app: live plots, PID step test, register editor, documentation;
  `--connect PORT`, `--host` (default: only reachable from this computer)
- Firmware for a bus IMU node on a Seeed XIAO nRF52840 Sense (`firmware/xiao_imu/`)
- Optional extras: the core only needs numpy and pyserial; `servolab[all]`
  installs everything
- Documentation website with guides, the Python API, the register tables and
  the examples, generated from the package
