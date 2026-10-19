"""
ServoScope entry point.

    uv run servoscope            # opens ServoScope in your browser
    uv run servoscope --sim      # connect to simulated motors right away
    uv run servoscope --sim so102   # a simulated SO102 arm (3D view in Rerun)
    uv run servoscope --connect tcp://emr-mobile-3.local   # motors of a robot, over WiFi
    uv run servoscope --host 0.0.0.0   # also reachable from other computers (careful!)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from nicegui import app, ui

from servolab.scope import theme
from servolab.scope.docs_view import DocsView
from servolab.scope.imu_view import ImuView
from servolab.scope.motor_view import MotorView
from servolab.scope.sidebar import Sidebar
from servolab.scope.state import SIM_PORT, scope_state

ASSETS = Path(__file__).parent / "assets"
LIVE_UPDATE_SECONDS = 0.1


class ScopePage:
    """One browser tab. All tabs share the same scope_state."""

    def __init__(self):
        self.state = scope_state
        self.sidebar = Sidebar(self.state, on_navigate=self.show_content, on_connection_change=self.after_connection_change)
        self.motor_view = MotorView(self.state, on_motors_changed=self.after_connection_change)
        self.imu_view = ImuView(self.state, on_devices_changed=self.after_connection_change)
        self.docs_view = DocsView()
        self.seen_connection = self.state.connection

    def build(self) -> None:
        """Build the page: sidebar, the content area and the timer for live values."""
        theme.apply_theme()
        self.sidebar.build()
        with ui.column().classes("sl-letterhead w-full max-w-[1480px] mx-auto px-8 py-8 gap-6"):
            theme.logo_stamp()
            self.content()
        ui.timer(LIVE_UPDATE_SECONDS, self.update_live)

    @ui.refreshable_method
    def content(self) -> None:
        """The main area: documentation, the selected IMU or the selected motor."""
        if self.state.view == "docs":
            self.docs_view.build()
        elif self.state.view == "sensor":
            self.imu_view.build()
        else:
            self.motor_view.build()

    def show_content(self) -> None:
        """Rebuild the main area (another device or the documentation was chosen)."""
        self.content.refresh()

    def after_connection_change(self) -> None:
        """Rebuild everything that depends on the connection and the devices found."""
        self.seen_connection = self.state.connection
        self.sidebar.connection_block.refresh()
        self.sidebar.device_list.refresh()
        self.sidebar.nav_block.refresh()
        self.content.refresh()

    def update_live(self) -> None:
        """Timer callback: refresh the live values, or rebuild if the connection changed."""
        # Connection changed in the background (e.g. cable unplugged)?
        if self.state.connection != self.seen_connection:
            if self.state.connection == "lost":
                ui.notify(self.state.connection_message, type="negative", multi_line=True, timeout=10000)
            self.after_connection_change()
            return
        self.sidebar.update_live()
        if self.state.view == "motor":
            self.motor_view.update_live()
            self.motor_view.status_chips.refresh()
        elif self.state.view == "sensor":
            self.imu_view.update_live()


@ui.page("/")
def index() -> None:
    """The only page of ServoScope. Every browser tab gets its own ScopePage."""
    ScopePage().build()


def main() -> None:
    """The servoscope command: parse the options, then start the web server."""
    parser = argparse.ArgumentParser(prog="servoscope", description="ServoScope - look at and play with Feetech motors.")
    parser.add_argument("--sim", nargs="?", const="sim", metavar="ROBOT",
                        help="connect to simulated motors on start; --sim so102 simulates a whole robot")
    parser.add_argument("--connect", metavar="PORT",
                        help="connect on start, e.g. /dev/ttyACM0 or tcp://emr-mobile-3.local")
    parser.add_argument("--port", type=int, default=8050, help="web server port (default 8050)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="network address of the web server; 0.0.0.0 lets other computers in "
                             "the network open ServoScope and move your motors (default: this computer only)")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    args = parser.parse_args()

    app.add_static_files("/servoscope-assets", ASSETS)
    app.on_shutdown(scope_state.disconnect)
    if args.sim:
        port = SIM_PORT if args.sim == "sim" else f"sim:{args.sim}"
        app.on_startup(lambda: scope_state.connect(port))
    elif args.connect:
        app.on_startup(lambda: scope_state.connect(args.connect))

    ui.run(
        title="ServoScope",
        favicon=ASSETS / "favicon.png",
        host=args.host,
        port=args.port,
        show=not args.no_browser,
        reload=False,
        show_welcome_message=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
