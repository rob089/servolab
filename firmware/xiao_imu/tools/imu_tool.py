"""imu_tool.py - talk to the bus IMU node with Feetech's own Python SDK.

Uses the official SDK bundled in servolab (servolab._sdk), so a passing test
also shows that Feetech's software can read our node.

    python imu_tool.py PORT                 live values (Ctrl+C to stop)
    python imu_tool.py PORT --check         protocol self-test
    python imu_tool.py PORT --set-id 101    give the IMU a new ID (saved)

PORT is the XIAO's own USB port (no bus hardware needed) or a bus adapter.
Options: --id (default: search 0..253), --baud (default 1000000).
"""

import argparse
import math
import struct
import sys
import time

from servolab._sdk import COMM_SUCCESS, GroupSyncRead, PortHandler
from servolab._sdk.imu import imu as ImuPacketHandler

MODEL_NUMBER = 2026
BROADCAST_ID = 0xFE

# Register addresses (see src/registers.h)
FIRMWARE_MAJOR, MODEL, ID, BAUD_RATE = 0, 3, 5, 6
GYRO_RANGE, ACC_RANGE, SAMPLE_RATE, LOCK = 11, 12, 13, 55
MEASUREMENTS, MEASUREMENTS_SIZE = 56, 23  # 56..78: quaternion, gyro, acc
G = 9.80665


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------

def half_float(low, high):
    """Two bytes (low first) of a 16-bit half float -> Python float."""
    return struct.unpack("<e", bytes([low, high]))[0]


def sign_magnitude(low, high):
    """Two bytes (low first), sign in bit 15 -> signed integer."""
    value = low | (high << 8)
    return -(value & 0x7FFF) if value & 0x8000 else value


def decode(data):
    """23 bytes from address 56 -> quaternion (w, x, y, z), gyro rad/s, acc m/s^2."""
    x, y, z = (half_float(data[i], data[i + 1]) for i in (0, 2, 4))
    w = math.sqrt(max(0.0, 1.0 - x * x - y * y - z * z))
    gyro = [sign_magnitude(data[i], data[i + 1]) / 1000.0 for i in (6, 9, 12)]   # mrad/s
    acc = [sign_magnitude(data[i], data[i + 1]) / 1000.0 * G for i in (15, 18, 21)]  # mg
    return (w, x, y, z), gyro, acc


def roll_pitch_yaw(q):
    """Quaternion (w, x, y, z) -> roll, pitch, yaw in degrees (rotation order z-y-x)."""
    w, x, y, z = q
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return [math.degrees(a) for a in (roll, pitch, yaw)]


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def open_port(name, baud):
    """Open the serial port with Feetech's SDK. Returns (port, packet handler)."""
    port = PortHandler(name)
    if not port.openPort() or not port.setBaudRate(baud):
        sys.exit(f"Could not open {name}")
    return port, ImuPacketHandler(port)


def read(sdk, imu_id, address, length):
    """Read `length` bytes from `address`. Returns (data, error byte); raises if nobody answers."""
    data, result, error = sdk.readTxRx(imu_id, address, length)
    if result != COMM_SUCCESS:
        raise RuntimeError(f"read failed: {sdk.getTxRxResult(result)}")
    return data, error


def write(sdk, imu_id, address, values):
    """Write a list of bytes to `address`; raises if nobody answers."""
    result, _ = sdk.writeTxRx(imu_id, address, len(values), values)
    if result != COMM_SUCCESS:
        raise RuntimeError(f"write failed: {sdk.getTxRxResult(result)}")


def find_imu(sdk, wanted_id):
    """The ID of the IMU: `wanted_id` if it answers, otherwise the first IMU found in 0...253."""
    ids = [wanted_id] if wanted_id is not None else range(0, 254)
    for imu_id in ids:
        model, result, _ = sdk.ping(imu_id)
        if result == COMM_SUCCESS and model == MODEL_NUMBER:
            return imu_id
    sys.exit("No IMU found (model number %d)." % MODEL_NUMBER)


def show_info(sdk, imu_id):
    """Print model, firmware and the settings of the IMU."""
    data, error = read(sdk, imu_id, 0, 14)
    print(f"IMU ID {imu_id}: model {data[3] | data[4] << 8}, firmware {data[0]}.{data[1]}, "
          f"baud code {data[BAUD_RATE]}, gyro range {data[GYRO_RANGE]}, acc range {data[ACC_RANGE]}, "
          f"rate code {data[SAMPLE_RATE]}" + ("  ** sensor error **" if error else ""))


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def monitor(sdk, imu_id):
    """Print orientation, gyro and accelerometer on one line, again and again (Ctrl+C stops)."""
    count, start = 0, time.time()
    rate = 0.0
    while True:
        data, error = read(sdk, imu_id, MEASUREMENTS, MEASUREMENTS_SIZE)
        q, gyro, acc = decode(data)
        count += 1
        if time.time() - start > 1:
            rate, count, start = count / (time.time() - start), 0, time.time()
        rpy = roll_pitch_yaw(q)
        print("\rrpy %7.1f %7.1f %7.1f deg | gyro %6.2f %6.2f %6.2f rad/s | acc %6.2f %6.2f %6.2f m/s^2 "
              "| |a| %5.2f | %4.0f reads/s %s" % (*rpy, *gyro, *acc, math.dist(acc, (0, 0, 0)), rate,
                                                  "ERR" if error else "   "), end="", flush=True)


def check(port, sdk, imu_id):
    """Exercise every instruction the node supports. Prints PASS/FAIL per test."""
    failures = 0

    def report(name, ok, detail=""):
        """Print one test result and count the failures."""
        nonlocal failures
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")

    def raw_exchange(packet, wait=0.05):
        """Send raw bytes, wait, and return whatever came back (b"" = no answer)."""
        port.clearPort()
        port.writePort(bytes(packet))
        time.sleep(wait)
        return port.ser.read(port.ser.in_waiting)

    def packet(pid, instruction, params):
        """Build an instruction packet: FF FF ID LENGTH INSTRUCTION PARAMS... CHECKSUM."""
        body = [pid, len(params) + 2, instruction, *params]
        return [0xFF, 0xFF, *body, (~sum(body)) & 0xFF]

    model, result, _ = sdk.ping(imu_id)
    report("ping returns model number", result == COMM_SUCCESS and model == MODEL_NUMBER, f"model={model}")

    data, _ = read(sdk, imu_id, 0, 80)
    report("read whole table", len(data) == 80 and data[ID] == imu_id)
    data, _ = read(sdk, imu_id, 250, 10)
    report("read past the end gives zeros", data == [0] * 10)

    q, gyro, acc = decode(read(sdk, imu_id, MEASUREMENTS, MEASUREMENTS_SIZE)[0])
    norm_q = math.sqrt(sum(c * c for c in q))
    report("quaternion has length 1", abs(norm_q - 1) < 0.01, f"|q|={norm_q:.4f}")
    norm_a = math.dist(acc, (0, 0, 0)) / G
    report("resting acceleration is about 1 g", 0.9 < norm_a < 1.1, f"|a|={norm_a:.3f} g")
    report("resting gyro is about 0", max(abs(g) for g in gyro) < 0.05, f"gyro={gyro}")

    old = read(sdk, imu_id, GYRO_RANGE, 1)[0][0]
    write(sdk, imu_id, GYRO_RANGE, [1])
    report("write gyro range", read(sdk, imu_id, GYRO_RANGE, 1)[0][0] == 1)
    write(sdk, imu_id, GYRO_RANGE, [9])
    report("invalid value is ignored", read(sdk, imu_id, GYRO_RANGE, 1)[0][0] == 1)
    write(sdk, imu_id, MODEL, [0, 0])
    report("read-only register is not changed", read(sdk, imu_id, MODEL, 2)[0] == [MODEL_NUMBER & 0xFF, MODEL_NUMBER >> 8])

    result, _ = sdk.regWriteTxRx(imu_id, GYRO_RANGE, 1, [2])
    before = read(sdk, imu_id, GYRO_RANGE, 1)[0][0]
    sdk.action(BROADCAST_ID)
    time.sleep(0.01)
    after = read(sdk, imu_id, GYRO_RANGE, 1)[0][0]
    report("REG_WRITE waits for ACTION", result == COMM_SUCCESS and before == 1 and after == 2, f"{before} -> {after}")
    write(sdk, imu_id, GYRO_RANGE, [old])

    group = GroupSyncRead(sdk, MEASUREMENTS, MEASUREMENTS_SIZE)
    group.addParam(imu_id)
    result = group.txRxPacket()
    ok = result == COMM_SUCCESS and group.isAvailable(imu_id, MEASUREMENTS, MEASUREMENTS_SIZE)[0]
    report("SYNC_READ", ok)

    answer = raw_exchange(packet(BROADCAST_ID, 0x01, []))
    report("no answer to broadcast PING", answer == b"", answer.hex())
    damaged = packet(imu_id, 0x01, [])
    damaged[-1] ^= 0xFF
    answer = raw_exchange(damaged)
    report("no answer to damaged packet", answer == b"", answer.hex())
    answer = raw_exchange(packet(imu_id, 0x01, []))
    # A status packet looks like an instruction packet with ERROR (0) in place of the instruction.
    report("raw PING answer", answer == bytes(packet(imu_id, 0x00, [])), answer.hex())

    write(sdk, imu_id, ACC_RANGE, [0])
    answer = raw_exchange(packet(imu_id, 0x0A, []))  # RESET: factory defaults, keeps the ID
    defaults = read(sdk, imu_id, ACC_RANGE, 1)[0][0]
    report("RESET restores defaults, keeps ID", len(answer) == 6 and defaults == 2 and
           read(sdk, imu_id, ID, 1)[0][0] == imu_id, f"acc range={defaults}")

    print("all tests passed" if failures == 0 else f"{failures} test(s) FAILED")
    return failures == 0


def set_id(sdk, imu_id, new_id):
    """Give the IMU a new ID and save it in flash."""
    write(sdk, imu_id, LOCK, [0])        # unlock: the change is saved in flash
    write(sdk, imu_id, ID, [new_id])     # answered with the old ID, then the new one is active
    write(sdk, new_id, LOCK, [1])
    print(f"ID {imu_id} -> {new_id}")


def main():
    """Command line: see the top of this file."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("port")
    parser.add_argument("--id", type=int, default=None)
    parser.add_argument("--baud", type=int, default=1_000_000)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--set-id", type=int, default=None)
    args = parser.parse_args()

    port, sdk = open_port(args.port, args.baud)
    imu_id = find_imu(sdk, args.id)
    show_info(sdk, imu_id)
    try:
        if args.check:
            sys.exit(0 if check(port, sdk, imu_id) else 1)
        elif args.set_id is not None:
            set_id(sdk, imu_id, args.set_id)
        else:
            monitor(sdk, imu_id)
    except KeyboardInterrupt:
        print()
    finally:
        port.closePort()


if __name__ == "__main__":
    main()
