# Modes and units

## Units

servolab always uses SI units.

| Value        | Unit                                   |
|--------------|----------------------------------------|
| position     | rad, 0 = middle of the motor, −π … +π  |
| velocity     | rad/s                                  |
| current      | A                                      |
| voltage      | V                                      |
| temperature  | °C                                     |
| load, PWM    | −1.0 … 1.0 (1.0 = 100 %)               |
| IMU acceleration | m/s² (includes gravity)            |
| IMU angular velocity | rad/s                          |
| IMU orientation | quaternion [w, x, y, z]             |

Raw register values (`m.read_register(...)`, the Settings section in ServoScope)
are the motor's own integers. The unit column tells you what one step means.

## Modes

| Mode       | You set        | The motor …                                         |
|------------|----------------|-----------------------------------------------------|
| `position` | `m.position`   | moves to the goal and holds it (internal PID)       |
| `velocity` | `m.velocity`   | turns at the goal speed (internal speed controller) |
| `pwm`      | `m.pwm`        | gets this fraction of the supply voltage – no controller, that's your job |

Switch with `m.mode = "velocity"`. servolab makes the switch safe: the motor stays where
it is (position), starts at 0 rad/s (velocity) or at 0 % PWM.

A command that does not fit the mode is refused with a hint, e.g. setting `m.velocity`
while the motor is in position mode.

## Saving settings

Settings like mode, limits and gains live in the motor's EEPROM area. When you change
them, they work immediately but are **lost after power-off**. To keep them:

```python
m.write_register("p_coefficient", 20, save=True)   # one value
m.save_to_eeprom()                                 # everything
```

Don't save in a loop: EEPROM wears out after many writes.
