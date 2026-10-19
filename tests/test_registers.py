import pytest

from servolab.errors import RegisterError
from servolab.registers import STS3215_REGISTERS, allowed_range, find_register


def test_addresses_do_not_overlap():
    used = {}
    for register in STS3215_REGISTERS:
        for address in range(register.address, register.address + register.size):
            assert address not in used, f"{register.name} overlaps {used[address]}"
            used[address] = register.name


def test_find_register():
    assert find_register("STS3215", "goal_position").address == 42
    with pytest.raises(RegisterError):
        find_register("STS3215", "does_not_exist")


def test_allowed_range():
    assert allowed_range(find_register("STS3215", "id")) == (0, 255)
    assert allowed_range(find_register("STS3215", "goal_position")) == (-32767, 32767)
