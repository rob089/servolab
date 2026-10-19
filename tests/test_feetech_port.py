"""FeetechPort tests without hardware, using a fake serial port that never answers."""

import pytest

import servolab
from servolab import _sdk
from servolab.ports import feetech_port
from servolab.ports.feetech_port import RESET_IMU, RESET_MOTOR, FeetechPort


class SilentSerial:
    """Accepts everything that is written, never answers."""

    in_waiting = 0

    def reset_input_buffer(self):
        pass

    def write(self, data):
        return len(data)

    def read(self, n):
        return b""

    def close(self):
        pass


def make_port():
    port = FeetechPort.__new__(FeetechPort)       # skip __init__ (no real serial port)
    port.name = "fake"
    port.sdk_port = _sdk.PortHandler("fake")
    port.sdk_port.ser = SilentSerial()
    port.sdk_port.is_open = True
    port.sdk_port.tx_time_per_byte = 0.01
    port.sdk = _sdk.protocol_packet_handler(port.sdk_port, 0)
    return port


def test_stuck_busy_flag_after_ctrl_c_does_not_block_the_port():
    port = make_port()
    port.sdk_port.is_using = True                 # what Ctrl+C mid-message leaves behind
    with pytest.raises(servolab.NoResponseError):  # i.e. the message was sent, not refused
        port.read(1, 56, 2)


class RecordingSdk:
    """Remembers which instructions were sent. Answers only the ones in `answers_to`."""

    def __init__(self, answers_to):
        self.answers_to = answers_to
        self.sent = []

    def txRxPacket(self, packet):
        instruction = packet[_sdk.PKT_INSTRUCTION]
        self.sent.append(instruction)
        if instruction in self.answers_to:
            return [], _sdk.COMM_SUCCESS, 0
        return [], _sdk.COMM_RX_TIMEOUT, 0


def test_factory_reset_of_a_motor_uses_instruction_6():
    port = make_port()
    port.sdk = RecordingSdk(answers_to={RESET_MOTOR})
    port.factory_reset(1)
    assert port.sdk.sent == [RESET_MOTOR]


def test_factory_reset_of_an_imu_falls_back_to_instruction_10():
    port = make_port()
    port.sdk = RecordingSdk(answers_to={RESET_IMU})     # the IMU firmware does not know 0x06
    port.factory_reset(100)
    assert port.sdk.sent == [RESET_MOTOR, RESET_IMU]


class CollidingSdk:
    """Answers reads and pings with the given result codes, one after another."""

    def __init__(self, results):
        self.results = list(results)

    def next_result(self):
        return self.results.pop(0) if self.results else _sdk.COMM_SUCCESS

    def readTxRx(self, motor_id, address, size):
        return [0] * size, self.next_result(), 0

    def ping(self, motor_id):
        return 777, self.next_result(), 0


def test_ping_asks_again_after_a_garbled_answer():
    port = make_port()
    port.sdk = CollidingSdk([_sdk.COMM_RX_CORRUPT, _sdk.COMM_RX_CORRUPT])
    assert port.ping(1) == 777


def test_garbled_answers_mean_the_id_is_used_twice(monkeypatch):
    monkeypatch.setattr(feetech_port, "SECOND_ANSWER_WAIT", 0)
    port = make_port()
    port.sdk = CollidingSdk([_sdk.COMM_RX_CORRUPT])                          # once: could be noise
    assert not port.id_used_twice(1)
    port.sdk = CollidingSdk([_sdk.COMM_RX_CORRUPT, _sdk.COMM_SUCCESS, _sdk.COMM_RX_CORRUPT])
    assert port.id_used_twice(1)


def test_bytes_after_the_answer_mean_the_id_is_used_twice(monkeypatch):
    monkeypatch.setattr(feetech_port, "SECOND_ANSWER_WAIT", 0)
    port = make_port()
    port.sdk = CollidingSdk([])
    assert not port.id_used_twice(1)
    port.sdk_port.ser.in_waiting = 1        # a second answer left a byte behind
    assert port.id_used_twice(1)
