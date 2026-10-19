"""Tests for the simulated SO102 robot (needs: pip install "servolab[sim]").

The simulation runs in real time, so these tests take a few seconds.
"""
import math
import time

import pytest

import servolab

pytest.importorskip("mujoco")


@pytest.fixture
def bus():
    bus = servolab.connect("sim:so102", show=False)
    yield bus
    bus.disconnect()


def hold_zero(bus):
    for m in bus.motors.values():
        m.mode = "position"
        m.torque_enabled = True
        m.position = 0.0
    time.sleep(0.5)


def test_finds_the_seven_motors(bus):
    assert list(bus.motors) == [1, 2, 3, 4, 5, 6, 7]
    assert bus[1].model == "STS3215"


def test_unknown_robot_lists_the_known_ones():
    with pytest.raises(servolab.ServoLabError, match="so102"):
        servolab.connect("sim:no_such_robot", show=False)


def test_arm_sags_without_torque(bus):
    time.sleep(0.5)
    assert bus[2].position < -0.2      # shoulder lift falls forward


def test_holds_against_gravity(bus):
    hold_zero(bus)
    for motor_id in bus.motors:
        assert abs(bus[motor_id].position) < math.radians(2)
    assert bus[2].current > 0.3        # the shoulder works to hold the arm up


def test_move_with_speed_limit(bus):
    hold_zero(bus)
    start = time.perf_counter()
    bus[1].move_to(1.0, speed=2.0, wait=True)
    took = time.perf_counter() - start
    assert abs(bus[1].position - 1.0) < 0.02
    assert 0.4 < took < 1.0            # 1 rad at 2 rad/s


def test_velocity_mode(bus):
    hold_zero(bus)                     # lift the arm, or it drags over the floor
    m = bus[1]
    m.mode = "velocity"
    m.torque_enabled = True
    m.velocity = 1.0
    time.sleep(0.5)
    assert abs(m.velocity - 1.0) < 0.15


def test_positive_pwm_turns_to_larger_angles(bus):
    hold_zero(bus)
    m = bus[1]
    m.mode = "pwm"
    m.torque_enabled = True
    m.pwm = 0.3
    time.sleep(0.2)
    assert m.velocity > 0.3


def test_set_zero(bus):
    hold_zero(bus)
    bus[1].move_to(0.5, wait=True)
    bus[1].set_zero()
    assert abs(bus[1].position) < 0.02


def test_factory_reset(bus):
    bus[1].pid = (50, 1, 10)
    bus[1].factory_reset()
    assert bus[1].pid == (32, 0, 32)
    assert list(bus.motors) == [1, 2, 3, 4, 5, 6, 7]
    bus[2].factory_reset()          # in the middle of the chain: every motor keeps its ID
    assert bus.scan() == [1, 2, 3, 4, 5, 6, 7]


TWO_JOINTS_ONE_ID = """
<mujoco>
  <worldbody>
    <body name="link1">
      <joint name="j1" type="hinge"/>
      <geom type="capsule" fromto="0 0 0 0.1 0 0" size="0.01"/>
      <body name="link2" pos="0.1 0 0">
        <joint name="j2" type="hinge"/>
        <geom type="capsule" fromto="0 0 0 0.1 0 0" size="0.01"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <motor name="j1" joint="j1" ctrlrange="-2.9 2.9"/>
    <motor name="j2" joint="j2" ctrlrange="-2.9 2.9"/>
  </actuator>
  <custom>
    <numeric name="servo_id:j1" data="1"/>
    <numeric name="servo_id:j2" data="1"/>
  </custom>
</mujoco>
"""


def test_a_model_with_one_id_for_two_joints_is_refused(tmp_path):
    model = tmp_path / "two_joints_one_id.xml"
    model.write_text(TWO_JOINTS_ONE_ID)
    with pytest.raises(servolab.ServoLabError, match="servo ID 1 is given to two joints"):
        servolab.connect(f"sim:{model}", show=False)
