"""
ServoScope - a web app to look at and play with Feetech motors.

Start it with:  uv run servoscope   (or: python -m servolab.scope)

Unlike the rest of servolab, this part is not meant to be read by beginners:
it is an app, not a library. See scope/app.py for the entry point.
"""


def main() -> None:
    """Entry point of the servoscope command. Checks that NiceGUI is installed first."""
    try:
        import nicegui  # noqa: F401
    except ImportError:
        raise SystemExit('ServoScope needs NiceGUI. Install it with:  pip install "servolab[scope]"') from None
    from servolab.scope.app import main as run
    run()
