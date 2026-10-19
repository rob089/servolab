# Bundled Feetech SDK (`_sdk`)

This folder is an **unchanged copy** of the official Feetech Python SDK
(`scservo_sdk` from https://github.com/ftservo/FTServo_Python, commit `cbcfa64`,
MIT license, see `LICENSE`).

Why a copy instead of `pip install`?

- Two pip packages (`feetech-servo-sdk`, used by LeRobot, and
  `ftservo-python-sdk`) both install a module called `scservo_sdk`. Having our
  own copy avoids clashes when servolab and LeRobot live in the same environment.
- We know exactly which version we use.

The underscore in `_sdk` means "internal": you never need to import from here.
Only `servolab/ports/feetech_port.py` talks to this code.

To update: copy the new `scservo_sdk/*.py` files over these and update the
commit hash above. Do not edit the files in place.
