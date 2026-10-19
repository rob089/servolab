"""
server.py - share the motors on this computer's USB adapter over the network.

Runs on the small computer of a robot (e.g. a Raspberry Pi):

    servolab-server                         # first Waveshare adapter, TCP port 6100
    servolab-server --port /dev/ttyACM0     # a given serial port
    servolab-server --port sim              # simulated motors, for testing

and on the laptop:

    bus = servolab.connect("tcp://emr-mobile-3.local")

Only one program can use the motors at a time (as with a USB cable). A second
one gets a "busy" error.

Safety: when the connection breaks or the client says nothing for 1 s (it
normally sends a heartbeat every 0.2 s, see ports/network_port.py), the
server switches all motors off.
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time

from servolab.errors import NoResponseError, ServoLabError
from servolab.ports.network_port import DEFAULT_TCP_PORT, PROTOCOL_VERSION
from servolab.registers import MODEL_NAMES, find_register

WATCHDOG_SECONDS = 1.0


def log(text):
    """Print a line with the time in front, e.g. "14:02:11 192.168.4.2:51234 connected"."""
    print(time.strftime("%H:%M:%S"), text, flush=True)


class BusServer:
    """Answers the requests of one NetworkPort at a time with a real (or simulated) port."""

    def __init__(self, port, host="0.0.0.0", tcp_port=DEFAULT_TCP_PORT, watchdog_seconds=WATCHDOG_SECONDS):
        self.port = port
        self.watchdog_seconds = watchdog_seconds
        self.listener = socket.create_server((host, tcp_port))
        self.address = self.listener.getsockname()      # (host, port) - port is chosen if tcp_port = 0
        self.client = None                              # address of the client using the motors
        self.client_lock = threading.Lock()
        self.models = {}                                # {device ID: model name}, learnt from pings
        self.running = True

    def serve_forever(self):
        """Wait for clients and answer them, until shutdown(). Each client gets its own thread."""
        log(f"servolab-server on {self.port.name}, listening on port {self.address[1]}")
        while self.running:
            try:
                connection, address = self.listener.accept()
            except OSError:
                break       # shutdown() closed the listener
            threading.Thread(target=self.handle, args=(connection, address), daemon=True).start()

    def shutdown(self):
        """Stop accepting clients (serve_forever() then returns)."""
        self.running = False
        self.listener.close()

    # -- one client ----------------------------------------------------------

    def handle(self, connection, address):
        """Talk to one client until it disconnects or stays silent too long.

        Only one client may use the motors at a time; a second one gets an
        error and is disconnected. Whenever a client leaves, for whatever
        reason, all motors are switched off.
        """
        name = f"{address[0]}:{address[1]}"
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        reader = connection.makefile("r", encoding="utf-8")
        with self.client_lock:
            busy = self.client is not None
            if not busy:
                self.client = name
        if busy:
            # Read the client's "hello" first: on Windows, closing a connection that
            # still holds unread data throws away our answer before the client sees it.
            connection.settimeout(self.watchdog_seconds)
            try:
                reader.readline()
            except OSError:
                pass
            self.reply_error(connection, "PortError", f"The motors are already used by {self.client}.")
            connection.close()
            return

        log(f"{name} connected")
        connection.settimeout(self.watchdog_seconds)
        reason = "disconnected"
        try:
            while True:
                try:
                    line = reader.readline()
                except socket.timeout:
                    reason = f"silent for {self.watchdog_seconds} s"
                    break
                if not line:
                    break
                self.answer(connection, json.loads(line))
        except (OSError, ValueError) as error:
            reason = f"connection error ({error})"
        finally:
            self.torque_off_all()
            log(f"{name} {reason}: all motors switched off")
            connection.close()
            with self.client_lock:
                self.client = None

    def answer(self, connection, request):
        """Run one request and send the result back, or the error it caused."""
        try:
            result = self.run(request)
        except NoResponseError as error:
            self.reply_error(connection, "NoResponseError", str(error), ids=error.motor_ids)
        except ServoLabError as error:
            self.reply_error(connection, type(error).__name__, str(error))
        else:
            connection.sendall((json.dumps({"ok": True, "result": result}) + "\n").encode("utf-8"))

    def run(self, request):
        """Call the port method the client asked for."""
        op = request["op"]
        if op in ("hello", "heartbeat"):
            if op == "hello" and request.get("version") != PROTOCOL_VERSION:
                raise ServoLabError("servolab on the laptop and on the robot have different versions. "
                                    "Update both.")
            return None
        if op == "ping":
            if request.get("timeout_ms") is None:
                model = self.port.ping(request["id"])
            else:
                model = self.port.ping(request["id"], timeout_ms=request["timeout_ms"])
            if model is not None:
                self.models[request["id"]] = MODEL_NAMES.get(model, "")
            return model
        if op == "read":
            return list(self.port.read(request["id"], request["address"], request["size"]))
        if op == "write":
            self.port.write(request["id"], request["address"], request["data"])
            return None
        if op == "sync_read":
            answers = self.port.sync_read(request["ids"], request["address"], request["size"])
            return {str(device_id): list(data) for device_id, data in answers.items()}
        if op == "sync_write":
            data = {int(device_id): values for device_id, values in request["data"].items()}
            self.port.sync_write(request["ids"], request["address"], data)
            return None
        if op == "factory_reset":
            self.port.factory_reset(request["id"])
            return None
        if op == "id_used_twice":
            return self.port.id_used_twice(request["id"])
        raise ServoLabError(f"Unknown request '{op}'.")

    def reply_error(self, connection, kind, message, **extra):
        """Send an error answer. `kind` is the name of the servolab error class."""
        reply = {"ok": False, "error": kind, "message": message, **extra}
        try:
            connection.sendall((json.dumps(reply) + "\n").encode("utf-8"))
        except OSError:
            pass

    def torque_off_all(self):
        """Switch off every motor the client has found (devices without torque, e.g. IMUs, are skipped)."""
        for device_id, model in self.models.items():
            try:
                register = find_register(model, "torque_enable")
            except ServoLabError:
                continue
            try:
                self.port.write(device_id, register.address, [0])
            except ServoLabError:
                pass      # keep switching off the others


def open_port(name):
    """The port for --port: a serial port, "sim" or "sim:<robot>"."""
    from servolab.ports.feetech_port import FeetechPort, find_adapter
    from servolab.ports.sim_port import SimPort
    if name is None:
        return FeetechPort(find_adapter())
    if name == "sim":
        return SimPort((1, 2, 3))
    if name.startswith("sim:"):
        from servolab.ports.mujoco_port import MujocoPort
        return MujocoPort(name[len("sim:"):], show=False)
    return FeetechPort(name)


def main():
    """The servolab-server command: servolab-server [--port PORT] [--listen HOST:PORT]."""
    parser = argparse.ArgumentParser(prog="servolab-server",
                                     description="Share the motors on this computer over the network.")
    parser.add_argument("--port", help="serial port (default: find the Waveshare adapter), 'sim' or 'sim:<robot>'")
    parser.add_argument("--listen", default=f"0.0.0.0:{DEFAULT_TCP_PORT}",
                        help=f"address and TCP port to listen on (default 0.0.0.0:{DEFAULT_TCP_PORT})")
    args = parser.parse_args()

    host, _, tcp_port = args.listen.partition(":")
    server = BusServer(open_port(args.port), host=host, tcp_port=int(tcp_port or DEFAULT_TCP_PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        server.torque_off_all()


if __name__ == "__main__":
    main()
