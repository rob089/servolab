"""NetworkPort + servolab-server, both on this computer, with simulated motors."""

import socket
import threading
import time

import pytest

import servolab
from servolab.bus import Bus
from servolab.ports.network_port import NetworkPort
from servolab.ports.sim_port import SimPort
from servolab.server import BusServer

TORQUE_ENABLE = 40     # address of torque_enable in the STS3215


@pytest.fixture
def server():
    server = BusServer(SimPort((1, 2, 3)), host="127.0.0.1", tcp_port=0, watchdog_seconds=0.5)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


def address(server):
    return f"127.0.0.1:{server.address[1]}"


def torque_in_simulation(server, motor_id):
    return server.port.motors[motor_id].memory[TORQUE_ENABLE]


def test_bus_over_the_network_works_like_usb(server):
    bus = servolab.connect(f"tcp://{address(server)}")
    assert sorted(bus.motors) == [1, 2, 3]
    bus[1].torque_enabled = True
    bus[1].position = 0.4
    time.sleep(0.6)
    fb = bus.read_feedback()
    assert abs(fb.of(1)["position"] - 0.4) < 0.05
    bus[2].pid = (40, 0, 20)
    assert bus[2].pid == (40, 0, 20)
    bus.disconnect()


def test_errors_come_back_as_servolab_errors(server):
    bus = Bus(NetworkPort(address(server)))
    with pytest.raises(servolab.NoResponseError):
        bus.read_bytes(9, 56, 2)           # there is no motor 9
    assert bus.port.ping(9) is None
    bus.disconnect()


def test_second_client_gets_busy(server):
    first = Bus(NetworkPort(address(server)))
    with pytest.raises(servolab.PortError, match="already used"):
        NetworkPort(address(server))
    first.disconnect()
    time.sleep(0.2)
    second = Bus(NetworkPort(address(server)))    # free again
    second.disconnect()


def test_heartbeat_keeps_an_idle_client_connected(server):
    bus = servolab.connect(f"tcp://{address(server)}")
    bus[1].torque_enabled = True
    time.sleep(1.5)                        # longer than the watchdog, but heartbeats keep coming
    assert torque_in_simulation(server, 1) == 1
    assert bus[1].torque_enabled
    bus.disconnect()


def test_watchdog_switches_motors_off_when_the_client_goes_silent(server):
    bus = servolab.connect(f"tcp://{address(server)}")
    bus[1].torque_enabled = True
    bus[2].torque_enabled = True
    bus.port.connected = False             # stops the heartbeat thread, like a frozen program ...
    time.sleep(1.2)                        # ... without closing the connection
    assert torque_in_simulation(server, 1) == 0
    assert torque_in_simulation(server, 2) == 0


def test_watchdog_switches_motors_off_when_the_connection_breaks(server):
    bus = servolab.connect(f"tcp://{address(server)}")
    bus[3].torque_enabled = True
    bus.port.socket.shutdown(socket.SHUT_RDWR)   # like WiFi gone or the program killed
    time.sleep(0.3)
    assert torque_in_simulation(server, 3) == 0
    with pytest.raises(servolab.PortError, match="Lost the connection"):
        bus[3].position = 0.1


def test_unreachable_robot_gives_a_helpful_error():
    with pytest.raises(servolab.PortError, match="robot's WiFi"):
        NetworkPort("127.0.0.1:1")         # nothing listens there


def test_duplicate_ids_are_found_over_the_network():
    server = BusServer(SimPort((1, 1, 2)), host="127.0.0.1", tcp_port=0, watchdog_seconds=0.5)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        bus = Bus(NetworkPort(address(server)))
        with pytest.raises(servolab.DuplicateIdError):
            bus.scan(range(0, 5))
        bus.disconnect()
    finally:
        server.shutdown()
