"""IMU support: scan, decoding, read_feedback() with sensors, settings, ID change.

There is no simulated IMU in servolab, so these tests use a small fake port:
simulated motors (SimPort) plus one fake XIAO IMU memory table.
"""

import math
import struct

import numpy as np
import pytest

import servolab
from servolab.bus import Bus
from servolab.errors import NoResponseError, RegisterError
from servolab.ports.sim_port import SimPort

IMU_ID = 100


def half(value):
    """Python float -> 16-bit half float as an integer."""
    return struct.unpack("<H", struct.pack("<e", value))[0]


def put(memory, address, value):
    memory[address] = value & 0xFF
    memory[address + 1] = value >> 8


class FakeImuPort:
    """Motors from SimPort, plus one IMU that answers like the XIAO firmware."""

    def __init__(self, motor_ids=(1, 2), combined_sync_read_works=True, imu_answers=True):
        self.name = "fake"
        self.sim = SimPort(motor_ids)
        self.combined_sync_read_works = combined_sync_read_works
        self.imu_answers = imu_answers
        self.sync_reads = []      # the ID lists of all sync reads, to check what was sent

        self.imu_id = IMU_ID
        self.memory = [0] * 256
        self.memory[0], self.memory[1] = 1, 0         # firmware 1.0
        put(self.memory, 3, 2026)                    # model number
        self.memory[5] = IMU_ID
        self.memory[11], self.memory[12], self.memory[13] = 3, 2, 4
        self.memory[55] = 1
        # Lying tilted by 30 deg around x: q = (cos 15deg, sin 15deg, 0, 0)
        put(self.memory, 56, half(math.sin(math.radians(15))))
        put(self.memory, 62, 1500)                   # +1.5 rad/s around x
        put(self.memory, 65, 0x8000 | 250)           # -0.25 rad/s around y
        put(self.memory, 71, 0)
        put(self.memory, 74, 500)                    # +0.5 g along y
        put(self.memory, 77, 866)                    # +0.866 g along z

    def close(self):
        pass

    def ping(self, device_id, timeout_ms=None):
        if device_id == self.imu_id:
            return 2026 if self.imu_answers else None
        return self.sim.ping(device_id)

    def read(self, device_id, address, size):
        if device_id == self.imu_id:
            if not self.imu_answers:
                raise NoResponseError(device_id)
            return self.memory[address:address + size]
        return self.sim.read(device_id, address, size)

    def write(self, device_id, address, data):
        if device_id != self.imu_id:
            return self.sim.write(device_id, address, data)
        if not self.imu_answers:
            raise NoResponseError(device_id)
        for i, value in enumerate(data):
            if address + i in (5, 11, 12, 13, 55):    # only these are writable
                self.memory[address + i] = value
        self.imu_id = self.memory[5]

    def sync_read(self, device_ids, address, size):
        self.sync_reads.append(list(device_ids))
        has_imu = self.imu_id in device_ids
        if has_imu and (not self.imu_answers or (len(device_ids) > 1 and not self.combined_sync_read_works)):
            raise NoResponseError([self.imu_id])
        return {device_id: self.read(device_id, address, size) for device_id in device_ids}

    def sync_write(self, device_ids, address, data_per_id):
        self.sim.sync_write(device_ids, address, data_per_id)

    def factory_reset(self, device_id):
        if device_id != self.imu_id:
            return self.sim.factory_reset(device_id)
        self.memory[11], self.memory[12], self.memory[13] = 3, 2, 4   # like the firmware: keeps the ID

    def id_used_twice(self, device_id):
        return device_id != self.imu_id and self.sim.id_used_twice(device_id)


def make_bus(**options):
    bus = Bus(FakeImuPort(**options))
    bus.scan(range(0, 110))
    return bus


@pytest.fixture
def bus():
    bus = make_bus()
    yield bus
    bus.disconnect()


def test_scan_puts_imus_into_sensors(bus):
    assert list(bus.motors) == [1, 2]
    assert list(bus.sensors) == [IMU_ID]
    imu = bus[IMU_ID]
    assert isinstance(imu, servolab.Imu)
    assert imu.model == "XIAO IMU"
    assert "sensors [100]" in repr(bus)


def test_read_decodes_si_units(bus):
    fb = bus[IMU_ID].read()
    assert np.allclose(fb.acceleration, [0, 0.5 * 9.80665, 0.866 * 9.80665])
    assert np.allclose(fb.angular_velocity, [1.5, -0.25, 0])
    angle = math.radians(15)
    assert np.allclose(fb.quaternion, [math.cos(angle), math.sin(angle), 0, 0], atol=1e-3)
    assert np.allclose(bus[IMU_ID].acceleration, fb.acceleration)


def test_read_feedback_reads_motors_and_imu_with_one_message(bus):
    port = bus.port
    port.sync_reads.clear()
    fb = bus.read_feedback()
    assert port.sync_reads == [[1, 2, IMU_ID]]      # one message, IMU last
    assert fb.ids == [1, 2]
    assert len(fb.position) == 2
    assert np.allclose(fb.sensors[IMU_ID].angular_velocity, [1.5, -0.25, 0])
    assert np.allclose(fb.of(IMU_ID)["angular_velocity"], [1.5, -0.25, 0])
    assert "position" in fb.of(1)


def test_read_feedback_without_sensors_is_unchanged():
    bus = Bus(SimPort((1, 2)))
    bus.scan(range(0, 5))
    fb = bus.read_feedback()
    assert fb.sensors == {}
    assert fb.ids == [1, 2]
    bus.disconnect()


def test_read_feedback_with_ids_picks_motors_and_sensors(bus):
    fb = bus.read_feedback(ids=[IMU_ID, 2])
    assert fb.ids == [2]
    assert list(fb.sensors) == [IMU_ID]


def test_falls_back_to_separate_reads_if_combined_sync_read_fails():
    bus = make_bus(combined_sync_read_works=False)
    fb = bus.read_feedback()
    assert np.allclose(fb.sensors[IMU_ID].angular_velocity, [1.5, -0.25, 0])
    assert len(fb.position) == 2
    assert bus.combined_feedback is False
    bus.port.sync_reads.clear()
    bus.read_feedback()
    assert bus.port.sync_reads == [[1, 2]]           # no more combined attempts
    bus.disconnect()


def test_missing_imu_raises_and_keeps_combined_mode():
    bus = make_bus()
    bus.port.imu_answers = False
    with pytest.raises(NoResponseError):
        bus.read_feedback()
    assert bus.combined_feedback is True             # the IMU was gone, not the combined read
    bus.disconnect()


def test_settings_in_real_units(bus):
    imu = bus[IMU_ID]
    assert (imu.gyro_range, imu.acc_range, imu.sample_rate) == (2000, 8, 416)
    imu.gyro_range = 500
    assert imu.read_register("gyro_range") == 1
    assert imu.gyro_range == 500
    with pytest.raises(RegisterError):
        imu.acc_range = 5
    assert imu.info["firmware"] == "1.0"


def test_change_imu_id(bus):
    bus[IMU_ID].id = 101
    assert list(bus.sensors) == [101]
    assert bus[101].id == 101
    with pytest.raises(RegisterError):
        bus[101].id = 1                               # taken by a motor


def test_factory_reset_restores_settings_and_keeps_id(bus):
    imu = bus[IMU_ID]
    imu.gyro_range = 500
    imu.sample_rate = 52
    imu.factory_reset()
    assert (imu.gyro_range, imu.acc_range, imu.sample_rate) == (2000, 8, 416)
    assert list(bus.sensors) == [IMU_ID]


def test_typo_gives_error(bus):
    with pytest.raises(AttributeError):
        bus[IMU_ID].acceleraton = 1
