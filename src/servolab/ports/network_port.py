"""
network_port.py - motors on another computer, over WiFi or Ethernet.

A mobile robot has its own small computer (e.g. a Raspberry Pi) with the USB
adapter and the motors. That computer runs  servolab-server  (see server.py),
and your laptop connects to it:

    bus = servolab.connect("tcp://emr-mobile-3.local")     # or "tcp://192.168.4.1"

After that, everything works as with a USB cable: bus.motors, read_feedback(),
ServoScope ... Only the time per message is longer (WiFi: a few milliseconds).

How it works: each of the six port methods (see feetech_port.py) is sent as one
line of JSON to the server, which calls the same method on its real port and
sends the answer back. Errors (e.g. a motor that does not answer) come back
as the same Python errors as with a USB cable.

Safety: a background thread sends a short "I am still here" message every
0.2 s. If the server hears nothing for 1 s (WiFi gone, program crashed), it
switches all motors off.
"""

import json
import socket
import threading
import time

from servolab.errors import CommunicationError, NoResponseError, PortError, ServoLabError

DEFAULT_TCP_PORT = 6100       # the TCP port servolab-server listens on
PROTOCOL_VERSION = 1
CONNECT_TIMEOUT = 3.0         # s, to reach the server at all
ANSWER_TIMEOUT = 2.0          # s, for one answer (a scan of one ID takes ~15 ms)
HEARTBEAT_SECONDS = 0.2       # how often we say "still here"


class NetworkPort:
    """Connection to servolab-server on another computer. Same methods as FeetechPort."""

    def __init__(self, address):
        """address: "host" or "host:port", e.g. "emr-mobile-3.local" or "192.168.4.1:6100"."""
        host, _, tcp_port = address.partition(":")
        self.name = f"tcp://{address}"
        try:
            self.socket = socket.create_connection((host, int(tcp_port or DEFAULT_TCP_PORT)),
                                                   timeout=CONNECT_TIMEOUT)
        except OSError as error:
            raise PortError(f"Could not reach {host}. Are you in the robot's WiFi, "
                            "and is servolab-server running?") from None
        self.socket.settimeout(ANSWER_TIMEOUT)
        # Send every message at once instead of waiting to collect more (faster for small messages)
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.reader = self.socket.makefile("r", encoding="utf-8")
        self.lock = threading.Lock()      # the heartbeat thread and your program share the connection
        self.connected = True
        self.lost_message = None          # why the connection broke, repeated on every later call

        try:
            self.request("hello", version=PROTOCOL_VERSION)   # the server says "busy" if someone else uses it
        except ServoLabError:
            self.close()
            raise

        self.heartbeat_thread = threading.Thread(target=self.heartbeat, name="servolab-heartbeat", daemon=True)
        self.heartbeat_thread.start()

    def close(self):
        """Close the connection. The server then switches all motors off."""
        self.connected = False
        try:
            self.socket.shutdown(socket.SHUT_RDWR)   # tell the server right away, even while
        except OSError:                              # the reader below still holds the socket
            pass
        self.reader.close()
        self.socket.close()

    # -- the six port methods (what they do: see feetech_port.py) -----------

    def ping(self, motor_id, timeout_ms=None):
        return self.request("ping", id=motor_id, timeout_ms=timeout_ms)

    def read(self, motor_id, address, size):
        return self.request("read", id=motor_id, address=address, size=size)

    def write(self, motor_id, address, data):
        self.request("write", id=motor_id, address=address, data=list(data))

    def sync_read(self, motor_ids, address, size):
        answers = self.request("sync_read", ids=list(motor_ids), address=address, size=size)
        return {int(motor_id): data for motor_id, data in answers.items()}   # JSON keys are text

    def sync_write(self, motor_ids, address, data_per_id):
        data = {str(motor_id): list(data_per_id[motor_id]) for motor_id in motor_ids}
        self.request("sync_write", ids=list(motor_ids), address=address, data=data)

    def factory_reset(self, motor_id):
        self.request("factory_reset", id=motor_id)

    def id_used_twice(self, motor_id):
        try:
            return self.request("id_used_twice", id=motor_id)
        except ServoLabError as error:
            if type(error) is ServoLabError:   # "Unknown request": an older servolab-server
                return False                    # can't check, so the check is skipped
            raise

    # -- sending and receiving ---------------------------------------------

    def request(self, op, **arguments):
        """Send one request, wait for the answer, turn an error answer into a Python error."""
        if not self.connected:
            raise PortError(self.lost_message or f"The connection to {self.name} is closed.")
        message = json.dumps({"op": op, **arguments}) + "\n"
        with self.lock:
            try:
                self.socket.sendall(message.encode("utf-8"))
                line = self.reader.readline()
            except OSError as error:      # includes the timeout
                self.connection_lost(f"no answer ({error})")
            if not line:
                self.connection_lost("the server closed the connection")
        answer = json.loads(line)
        if answer["ok"]:
            return answer.get("result")
        raise error_from_answer(answer)

    def heartbeat(self):
        """Background thread: tell the server "still here" every HEARTBEAT_SECONDS."""
        while self.connected:
            time.sleep(HEARTBEAT_SECONDS)
            try:
                self.request("heartbeat")
            except ServoLabError:
                return    # the next real request reports the problem

    def connection_lost(self, reason):
        """Close the connection and raise a PortError that explains what happened."""
        self.lost_message = f"Lost the connection to {self.name} ({reason}). The motors are off; connect again."
        self.close()
        raise PortError(self.lost_message)


def error_from_answer(answer):
    """The server's error description -> the matching servolab error."""
    kind = answer.get("error")
    message = answer.get("message", "")
    if kind == "NoResponseError":
        return NoResponseError(answer.get("ids", []))
    if kind == "CommunicationError":
        return CommunicationError(message)
    if kind == "PortError":
        return PortError(message)
    return ServoLabError(message)
