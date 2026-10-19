import time

import pytest

import servolab
from servolab.bus import Bus
from servolab.ports.sim_port import SimPort


@pytest.fixture
def bus():
    bus = Bus(SimPort((1, 2, 3)))
    bus.scan(range(0, 10))
    yield bus
    bus.disconnect()


def test_scan_finds_all_motors(bus):
    assert list(bus.motors) == [1, 2, 3]
    assert bus[1].model == "STS3215"


def test_unknown_id_gives_helpful_error(bus):
    with pytest.raises(servolab.PortError):
        bus[9]


def test_move_to(bus):
    m = bus[1]
    m.torque_enabled = True
    m.move_to(1.0, wait=True, timeout=3.0)
    assert abs(m.position - 1.0) < 0.02


def test_command_in_wrong_mode_is_refused(bus):
    with pytest.raises(servolab.RegisterError):
        bus[1].velocity = 1.0


def test_velocity_mode(bus):
    m = bus[2]
    m.mode = "velocity"
    m.torque_enabled = True
    m.velocity = 2.0
    time.sleep(0.4)
    assert abs(m.velocity - 2.0) < 0.1


def test_feedback_and_sync_write(bus):
    bus[2].torque_enabled = True
    bus[3].torque_enabled = True
    bus.write_positions({2: 0.5, 3: -0.5})
    time.sleep(1.0)
    fb = bus.read_feedback()
    assert fb.ids == [1, 2, 3]
    assert abs(fb.of(2)["position"] - 0.5) < 0.05
    assert abs(fb.of(3)["position"] + 0.5) < 0.05


def test_set_zero(bus):
    m = bus[1]
    m.torque_enabled = True
    m.move_to(1.0, wait=True, timeout=3.0)
    m.set_zero()
    assert abs(m.position) < 0.01
    m.torque_enabled = True          # must not jump back to the old goal
    time.sleep(0.3)
    assert abs(m.position) < 0.02


def test_zero_is_the_same_in_every_mode(bus):
    # The motor applies homing_offset only in position mode, servolab in the others.
    m = bus[1]
    m.torque_enabled = True
    m.move_to(1.0, wait=True, timeout=3.0)
    m.set_zero()
    for mode in ("pwm", "velocity", "position"):
        m.mode = mode
        assert abs(m.position) < 0.01, mode
        assert abs(bus.read_feedback(ids=[1]).position[0]) < 0.01, mode


def test_switching_from_pwm_to_position_does_not_jump(bus):
    m = bus[1]
    m.torque_enabled = True
    m.move_to(1.0, wait=True, timeout=3.0)
    m.set_zero()
    m.mode = "pwm"
    m.torque_enabled = True
    m.mode = "position"              # torque stays on: the goal must be "here"
    time.sleep(0.3)
    assert abs(m.position) < 0.02


def test_read_only_and_range_checks(bus):
    with pytest.raises(servolab.RegisterError):
        bus[1].write_register("present_position", 5)
    with pytest.raises(servolab.RegisterError):
        bus[1].write_register("id", 300)


def test_disconnect_stops_everything(bus):
    bus.disconnect()
    with pytest.raises(servolab.PortError):
        bus[1].position


def test_change_id(bus):
    bus[1].id = 7
    assert sorted(bus.motors) == [2, 3, 7]
    assert bus[7].id == 7
    assert bus.scan(range(0, 10)) == [2, 3, 7]      # the "real" motor really has the new ID
    bus[7].torque_enabled = True                    # and still works


def test_change_id_to_used_id_is_refused(bus):
    with pytest.raises(servolab.RegisterError):
        bus[1].id = 2


def test_factory_reset_restores_settings_and_keeps_id_and_zero():
    bus = Bus(SimPort((5,)))
    bus.scan(range(0, 10))
    m = bus[5]
    m.pid = (50, 1, 10)
    m.mode = "velocity"
    m.write_register("homing_offset", 300, save=True)
    m.factory_reset()
    assert bus.scan(range(0, 10)) == [5]            # the motor keeps its ID
    assert m.pid == (32, 0, 32)
    assert m.mode == "position"
    assert m.read_register("homing_offset") == 300  # the zero position is kept
    bus.disconnect()


def test_factory_reset_can_reset_the_zero_too(bus):
    bus[1].write_register("homing_offset", 300)
    bus[1].factory_reset(keep_zero=False)
    assert bus[1].read_register("homing_offset") == 0


def test_factory_reset_of_one_motor_in_a_chain(bus):
    bus[1].pid = (40, 0, 20)
    bus[2].pid = (50, 1, 10)
    bus[2].factory_reset()
    assert bus[2].pid == (32, 0, 32)
    assert bus[1].pid == (40, 0, 20)                # the other motors are not touched
    assert bus.scan(range(0, 10)) == [1, 2, 3]


def test_typo_in_attribute_name_raises(bus):
    with pytest.raises(AttributeError):
        bus[1].postion = 1.0


def test_positive_pwm_turns_towards_larger_angles(bus):
    m = bus[1]
    m.mode = "pwm"
    m.torque_enabled = True
    m.pwm = 0.3
    time.sleep(0.4)
    assert m.velocity > 0
    assert abs(m.pwm - 0.3) < 1e-9
    bus.write_pwms({1: -0.3})
    time.sleep(0.4)
    assert m.velocity < 0


def test_write_positions_accepts_feedback_array(bus):
    for motor_id in (1, 2, 3):
        bus[motor_id].torque_enabled = True
    goal = bus.read_feedback().position
    goal[0] = 0.8
    bus.write_positions(goal)
    time.sleep(1.0)
    assert abs(bus.read_feedback().of(1)["position"] - 0.8) < 0.05


def test_write_positions_array_with_ids(bus):
    bus[1].torque_enabled = True
    bus[3].torque_enabled = True
    bus.write_positions([0.4, -0.4], ids=[3, 1])
    time.sleep(1.0)
    fb = bus.read_feedback()
    assert abs(fb.of(3)["position"] - 0.4) < 0.05
    assert abs(fb.of(1)["position"] + 0.4) < 0.05


def test_write_positions_wrong_length_is_refused(bus):
    with pytest.raises(servolab.ServoLabError):
        bus.write_positions([0.1, 0.2])


def test_move_to_clears_goal_time_and_sets_speed(bus):
    m = bus[1]
    m.torque_enabled = True
    m.write_register("goal_time", 500)     # e.g. left over from PWM mode
    m.move_to(0.0, speed=0.5)
    assert m.read_register("goal_time") == 0
    assert m.read_register("goal_velocity") == servolab.units.rad_per_s_to_steps_per_s(0.5)
    assert m.read_register("goal_position") == servolab.units.rad_to_steps(0.0)


def test_move_to_speed_changes_duration(bus):
    m = bus[1]
    m.torque_enabled = True
    m.move_to(0.0, wait=True, timeout=3.0)
    start = time.perf_counter()
    m.move_to(1.0, speed=2.0, wait=True, timeout=5.0)
    fast = time.perf_counter() - start
    start = time.perf_counter()
    m.move_to(0.0, speed=0.5, wait=True, timeout=5.0)
    slow = time.perf_counter() - start
    # 1 rad at 0.5 rad/s takes at least 2 s, at 2 rad/s about 0.5 s. Polling and
    # settling add a constant bit to both, so don't expect the full factor 4.
    assert slow > 1.8
    assert slow > 2 * fast


def test_write_registers_refuses_gaps(bus):
    with pytest.raises(servolab.RegisterError):
        bus.write_registers(1, {"acceleration": 0, "goal_velocity": 0})


def test_bus_move_to_moves_all_and_waits(bus):
    bus[1].torque_enabled = True
    bus[2].torque_enabled = True
    bus.write_register(2, "goal_time", 500)     # e.g. left over from PWM mode
    bus.move_to([0.6, -0.2], ids=[1, 2], speed=2.0, wait=True, timeout=5.0)
    fb = bus.read_feedback(ids=[1, 2])
    assert abs(fb.of(1)["position"] - 0.6) < 0.03
    assert abs(fb.of(2)["position"] + 0.2) < 0.03
    assert bus.read_register(2, "goal_time") == 0


def test_bus_move_to_timeout(bus):
    bus[1].torque_enabled = True
    bus[1].move_to(0.0, wait=True, timeout=3.0)
    with pytest.raises(servolab.ServoLabError):
        bus.move_to({1: 2.0}, speed=0.2, wait=True, timeout=0.3)


def test_scan_stops_when_two_motors_have_the_same_id():
    bus = Bus(SimPort((1, 1, 2)))
    with pytest.raises(servolab.DuplicateIdError, match="Several devices have ID 1") as error:
        bus.scan(range(0, 10))
    assert error.value.ids == [1]
    bus.disconnect()


def test_connect_frees_the_port_after_a_duplicate_id():
    with pytest.raises(servolab.DuplicateIdError):
        servolab.connect("sim", sim_motor_ids=(3, 3))
    assert "sim" not in servolab.open_buses or not servolab.open_buses["sim"].connected
