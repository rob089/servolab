"""
feetech_port.py - the ONLY file that talks to the Feetech SDK.

A "port" sends bytes to the motors and receives their answers. It knows
nothing about positions or units, only about addresses and bytes.
Every port in servolab has the same seven methods:

    ping(motor_id)                               -> model number, or None
    read(motor_id, address, size)                -> list of bytes
    write(motor_id, address, data)               -> nothing
    sync_read(motor_ids, address, size)          -> {motor_id: list of bytes}
    sync_write(motor_ids, address, data_per_id)  -> nothing
    factory_reset(motor_id)                      -> nothing
    id_used_twice(motor_id)                      -> True if two devices answer to this ID

The simulated port (sim_port.py) has exactly the same methods, so the rest
of servolab does not care whether a real motor is connected.

The Feetech SDK reports problems as numbers ("result codes"). This file turns
them into readable Python errors (see errors.py).
"""

import errno
import time

import serial
import serial.tools.list_ports

from servolab import _sdk
from servolab._sdk import port_handler as sdk_port_handler
from servolab.errors import CommunicationError, NoResponseError, PortError

# USB vendor ID of WCH, the maker of the USB chip (CH343) on the Waveshare
# bus servo adapter. Used to find the adapter automatically.
WCH_VENDOR_ID = 0x1A86

# How long to wait for an answer, in milliseconds.
# The SDK default (50 ms) is fine during normal use. While scanning, most IDs
# are empty, and waiting 50 ms for each of 253 IDs would take over 12 seconds.
NORMAL_TIMEOUT_MS = 50
SCAN_TIMEOUT_MS = 10

# Instruction for a factory reset. The Feetech SDK's reSet() sends 0x0A, but
# STS motors ignore that: they reset with 0x06 (checked on an STS3215 with
# firmware 3.10). The servolab IMU firmware (firmware/xiao_imu/) uses 0x0A.
RESET_MOTOR = 0x06
RESET_IMU = 0x0A

# A garbled answer to a ping means somebody IS there, so ask again (up to this often).
PING_TRIES = 5

# Finding two devices with the same ID (see id_used_twice()): read this block
# (present_position ... present_current, values that differ between two motors)
# this many times. From DUPLICATE_LIMIT garbled or doubled answers on, the ID
# counts as used twice.
DUPLICATE_CHECK_ADDRESS = 56
DUPLICATE_CHECK_SIZE = 15
DUPLICATE_CHECK_READS = 20
DUPLICATE_LIMIT = 2
SECOND_ANSWER_WAIT = 0.003     # s, after an answer: by now a second answer has arrived too


def list_ports():
    """All serial ports of this computer, as a list of (name, description).

    Example: [('COM5', 'USB-SERIAL CH343 (Waveshare adapter?)')]
    """
    ports = []
    for info in serial.tools.list_ports.comports():
        description = info.description
        if info.vid == WCH_VENDOR_ID:
            description += " (Waveshare adapter?)"
        ports.append((info.device, description))
    return ports


def find_adapter():
    """Return the name of the one connected Waveshare adapter, or raise an error."""
    candidates = []
    for info in serial.tools.list_ports.comports():
        if info.vid == WCH_VENDOR_ID:
            candidates.append(info.device)

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) == 0:
        names = ", ".join(name for name, _ in list_ports()) or "none"
        raise PortError(f"No Waveshare adapter found. Is it plugged in? Ports: {names}")
    raise PortError(f"Several adapters found: {candidates}. Choose one: servolab.connect('{candidates[0]}')")


class FeetechPort:
    """Real connection to Feetech motors through a USB serial adapter."""

    def __init__(self, port_name, baudrate=1_000_000):
        self.name = port_name
        self.sdk_port = _sdk.PortHandler(port_name)
        # protocol_packet_handler builds and checks the messages.
        # The 0 means "low byte first", which is what STS motors use.
        self.sdk = _sdk.protocol_packet_handler(self.sdk_port, 0)

        try:
            self.sdk_port.baudrate = baudrate
            self.sdk_port.openPort()
        except serial.SerialException as error:
            if error.errno == errno.EACCES:
                reason = "no permission (Linux: join the dialout group)"
            elif error.errno == errno.ENOENT:
                reason = "there is no such port"
            else:
                reason = "is ServoScope or another program using it?"
            raise PortError(f"Could not open {port_name}: {reason}") from None

    def close(self):
        """Close the serial port, so that other programs can use the adapter."""
        self.sdk_port.closePort()

    # -- the six port methods ----------------------------------------------

    def ping(self, motor_id, timeout_ms=NORMAL_TIMEOUT_MS):
        """Ask "is anybody there with this ID?". Returns the model number or None."""
        # The SDK reads its timeout from a module-level setting, so we change
        # that setting for this one call and put it back afterwards.
        sdk_port_handler.LATENCY_TIMER = timeout_ms
        try:
            # A garbled answer means somebody is there (maybe two devices with
            # this ID, see id_used_twice()), so ask again instead of giving up.
            for _ in range(PING_TRIES):
                self._ready()
                try:
                    model_number, result, _ = self.sdk.ping(motor_id)
                except (serial.SerialException, OSError):
                    self._connection_lost()
                if result != _sdk.COMM_RX_CORRUPT:
                    break
        finally:
            sdk_port_handler.LATENCY_TIMER = NORMAL_TIMEOUT_MS

        if result == _sdk.COMM_SUCCESS:
            return model_number
        return None

    def read(self, motor_id, address, size):
        """Read `size` bytes, starting at `address`."""
        self._ready()
        try:
            data, result, _ = self.sdk.readTxRx(motor_id, address, size)
        except (serial.SerialException, OSError):
            self._connection_lost()
        self._check(result, motor_id)
        return data

    def write(self, motor_id, address, data):
        """Write a list of bytes, starting at `address`."""
        self._ready()
        try:
            result, _ = self.sdk.writeTxRx(motor_id, address, len(data), data)
        except (serial.SerialException, OSError):
            self._connection_lost()
        self._check(result, motor_id)

    def sync_read(self, motor_ids, address, size):
        """Read the same registers from several motors with ONE message.

        Much faster than reading each motor on its own. Returns a dict:
        {motor_id: list of bytes}.
        """
        self._ready()
        group = _sdk.GroupSyncRead(self.sdk, address, size)
        for motor_id in motor_ids:
            group.addParam(motor_id)
        try:
            group.txRxPacket()
        except (serial.SerialException, OSError):
            self._connection_lost()

        answers = {}
        missing = []
        for motor_id in motor_ids:
            # The SDK stores [error byte, data bytes ...] for every motor that
            # answered, and None for every motor that did not.
            stored = group.data_dict.get(motor_id)
            if stored:
                answers[motor_id] = stored[1:]
            else:
                missing.append(motor_id)

        if missing:
            raise NoResponseError(missing)
        return answers

    def sync_write(self, motor_ids, address, data_per_id):
        """Write to several motors with ONE message (they all react at the same time).

        data_per_id is a dict {motor_id: list of bytes}; all lists must have
        the same length.
        """
        self._ready()
        size = len(data_per_id[motor_ids[0]])
        group = _sdk.GroupSyncWrite(self.sdk, address, size)
        for motor_id in motor_ids:
            group.addParam(motor_id, data_per_id[motor_id])
        try:
            result = group.txPacket()
        except (serial.SerialException, OSError):
            self._connection_lost()
        self._check(result, motor_ids)

    # -- helpers -----------------------------------------------------------

    def factory_reset(self, motor_id):
        """Send the reset instruction: the device goes back to its factory settings.

        The device keeps its ID. A motor also loses its zero position
        (homing_offset becomes 0); bus.factory_reset() writes it back.

        Motors and the servolab IMU use different instructions (see RESET_MOTOR).
        A device that does not know an instruction does not answer, so we send
        the motor's first and, if nobody answers, the IMU's.
        """
        try:
            self._send_instruction(motor_id, RESET_MOTOR)
        except NoResponseError:
            self._send_instruction(motor_id, RESET_IMU)

    def id_used_twice(self, motor_id):
        """True if two (or more) devices seem to answer to this ID.

        Their answers collide on the cable: now and then an answer is garbled,
        or bytes of the second answer arrive after the first one. Often the
        answer even looks fine, but holds the values of only one of them.
        So we read the same block many times and count both kinds of trouble.
        Measured on STS3215 motors: one motor alone gave 0 of 120 such answers,
        two motors with the same ID about 4 in 10.
        """
        problems = 0
        for _ in range(DUPLICATE_CHECK_READS):
            self._ready()
            try:
                _, result, _ = self.sdk.readTxRx(motor_id, DUPLICATE_CHECK_ADDRESS, DUPLICATE_CHECK_SIZE)
                time.sleep(SECOND_ANSWER_WAIT)
                extra_bytes = self.sdk_port.ser.in_waiting    # the SDK only reads one answer
            except (serial.SerialException, OSError):
                self._connection_lost()
            if result == _sdk.COMM_RX_CORRUPT or extra_bytes > 0:
                problems += 1
        return problems >= DUPLICATE_LIMIT

    def _send_instruction(self, motor_id, instruction):
        """Send an instruction without parameters and wait for the answer.

        The SDK only has functions for the instructions it knows, so we build
        the message ourselves: FF FF  ID  LENGTH  INSTRUCTION  CHECKSUM.
        """
        self._ready()
        packet = [0] * 6
        packet[_sdk.PKT_ID] = motor_id
        packet[_sdk.PKT_LENGTH] = 2              # instruction + checksum
        packet[_sdk.PKT_INSTRUCTION] = instruction
        try:
            _, result, _ = self.sdk.txRxPacket(packet)   # adds header and checksum
        except (serial.SerialException, OSError):
            self._connection_lost()
        self._check(result, motor_id)

    def _ready(self):
        """Get the SDK ready for the next message.

        While a message is on its way, the SDK marks the port as "in use".
        If a program is stopped at exactly that moment (Ctrl+C), the mark
        stays, and every later message fails with "Port is in use!".
        servolab already makes sure that only one message is sent at a time
        (see the lock in bus.py), so we can safely clear the mark here.
        """
        self.sdk_port.is_using = False

    def _connection_lost(self):
        """Called when the operating system says the port is gone."""
        raise PortError(f"Lost the connection to {self.name}. Plug the USB cable in and connect again.") from None

    def _check(self, result, motor_id):
        """Turn the SDK's result code into an exception if something went wrong."""
        if result == _sdk.COMM_SUCCESS:
            return
        if result == _sdk.COMM_RX_TIMEOUT:
            raise NoResponseError(motor_id)
        if result == _sdk.COMM_RX_CORRUPT:
            raise CommunicationError(f"Garbled answer from motor {motor_id}. Check cables and power supply.")
        raise CommunicationError(
            f"Problem talking to motor {motor_id}: {self.sdk.getTxRxResult(result)}"
        )
