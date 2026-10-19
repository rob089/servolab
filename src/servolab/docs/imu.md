# IMU

An IMU (inertial measurement unit) measures how it turns (gyro) and how it
accelerates (accelerometer). The XIAO IMU sits on the motor bus like one more
motor, with its own ID (100 when it is new). `bus.scan()` puts it into
`bus.sensors`, not into `bus.motors`.

```python
bus = servolab.connect()
print(bus.sensors)            # {100: <Imu 100: XIAO IMU>}
imu = bus[100]                # like a motor: bus[ID]

fb = imu.read()               # everything from the same moment, ONE message
fb.acceleration               # [x, y, z] in m/s^2
fb.angular_velocity           # [x, y, z] in rad/s
fb.quaternion                 # orientation [w, x, y, z]
```

`imu.acceleration`, `imu.angular_velocity` and `imu.quaternion` also work, but
each of them is one message. In a loop, use `imu.read()` once.

## What the values mean

- **Angular velocity**: how fast the IMU turns around its x, y and z axis.
- **Acceleration**: includes gravity. Lying still, the IMU shows about
  9.81 m/s² pointing **up** (it measures the force that holds it against
  gravity). When it moves, gravity and its own acceleration add up.
- **Quaternion**: the IMU's own estimate of its orientation, from gyro and
  accelerometer together. It turns IMU coordinates into a world frame with
  z up. There is no compass: the heading (around z) starts at 0 and drifts
  slowly.

## Motors and IMUs together

`bus.read_feedback()` reads all motors **and** all sensors with one message:

```python
fb = bus.read_feedback()
fb.position                   # motors, as always
fb.sensors[100].acceleration  # the IMU with ID 100
fb.of(100)                    # as a dict, like fb.of(1) for a motor
```

## Settings

```python
imu.gyro_range = 2000         # deg/s: 250, 500, 1000 or 2000
imu.acc_range = 8             # g: 2, 4, 8 or 16
imu.sample_rate = 416         # Hz: 26, 52, 104, 208, 416 or 833
imu.save_to_eeprom()          # keep them after power-off
```

A smaller range measures finer steps, but values beyond it are cut off.
The values servolab gives you are in SI units for every setting.
