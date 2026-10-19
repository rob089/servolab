"""
ServoScope sidebar: logo, connection, motor and sensor list, navigation, emergency torque-off.
"""

from __future__ import annotations

import math
from typing import Callable

from nicegui import run, ui

import servolab
from servolab.errors import ServoLabError
from servolab.scope.state import SIM_PORT, ScopeState

SIM_LABEL = "Simulator (no hardware)"
DRAWER_WIDTH = 296


class Sidebar:
    """The left drawer. Callbacks tell the page when it has to rebuild the main area."""
    def __init__(self, state: ScopeState, on_navigate: Callable[[], None], on_connection_change: Callable[[], None]):
        self.state = state
        self.on_navigate = on_navigate                  # called when motor/docs selection changes
        self.on_connection_change = on_connection_change  # called after connect/disconnect/rescan
        self.port_select: ui.select | None = None
        self.device_widgets: dict[int, dict] = {}

    # ------------------------------------------------------------------
    def build(self) -> None:
        """Build the drawer once; the parts that change are refreshable methods."""
        with ui.left_drawer(value=True, fixed=True, bordered=True).props(f"width={DRAWER_WIDTH}").classes("p-0"):
            with ui.column().classes("w-full h-full no-wrap gap-0"):
                with ui.column().classes("w-full px-5 pt-7 pb-5 gap-2"):
                    ui.html("servoscope<i>.</i>").classes("sl-brand")
                    ui.label(f"servolab {servolab.__version__}").classes("sl-kicker")

                ui.separator()
                with ui.column().classes("w-full px-4 py-4 gap-3"):
                    ui.label("Connection").classes("sl-side-label")
                    self.connection_block()

                ui.separator()
                with ui.column().classes("w-full px-4 pt-4 gap-1 grow overflow-auto"):
                    self.device_list()

                with ui.column().classes("w-full px-4 pb-2 gap-1"):
                    self.nav_block()

                ui.separator()
                with ui.column().classes("w-full p-4"):
                    ui.button("All torque off", icon="power_settings_new", on_click=self.torque_off_all) \
                        .props("unelevated color=negative").classes("w-full sl-btn-main")

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def port_options(self) -> dict[str, str]:
        """Ports for the connection dropdown: serial ports, a typed robot address, the simulators."""
        options = {}
        for name, description in servolab.list_ports():
            # Hide macOS system ports nobody will ever want
            if "Bluetooth" in name or "debug-console" in name:
                continue
            options[name] = f"{name}  ·  {description}"
        if self.state.port_name and self.state.port_name.startswith("tcp://"):
            options[self.state.port_name] = self.state.port_name    # keep a typed robot address
        options[SIM_PORT] = SIM_LABEL
        for robot in simulated_robots():
            options[f"sim:{robot}"] = f"Simulated {robot.upper()} (3D)"
        return options

    def default_port(self, options: dict[str, str]) -> str | None:
        """Port preselected in the dropdown: the current one, else the first Waveshare adapter."""
        if self.state.port_name in options:
            return self.state.port_name
        for name, label in options.items():
            if "Waveshare" in label:
                return name
        return None

    @ui.refreshable_method
    def connection_block(self) -> None:
        """Connection status with Disconnect/rescan buttons, or the port choice with Connect."""
        state = self.state
        options = self.port_options()

        if state.connection == "connected":
            with ui.element("div").classes("sl-conn sl-conn-ok"):
                with ui.row().classes("items-center gap-2 no-wrap"):
                    ui.icon("check_circle", size="18px")
                    label = port_label(state.port_name)
                    ui.label(f"Connected · {label}").classes("ellipsis")
                ui.label(found_text(state)).classes("text-xs font-medium opacity-80 mt-0.5")
            with ui.row().classes("w-full gap-2 no-wrap"):
                ui.button("Disconnect", icon="link_off", on_click=self.disconnect) \
                    .props("outline color=negative").classes("grow")
                ui.button(icon="refresh", on_click=self.rescan).props("outline color=dark") \
                    .tooltip("Scan the bus again")
            return

        if state.connection == "lost":
            with ui.element("div").classes("sl-conn sl-conn-lost"):
                with ui.row().classes("items-center gap-2 no-wrap"):
                    ui.icon("error", size="18px")
                    ui.label("Connection lost")
                ui.label(state.connection_message).classes("text-xs font-medium opacity-90 mt-0.5")

        with ui.row().classes("w-full items-center gap-2 no-wrap"):
            # Typing is allowed too, e.g. tcp://emr-mobile-3.local for the motors of a robot over WiFi
            self.port_select = ui.select(options, value=self.default_port(options), label="Port or tcp://robot",
                                         with_input=True, new_value_mode="add-unique") \
                .props("outlined dense options-dense").classes("grow min-w-0")
            ui.button(icon="refresh", on_click=self.connection_block.refresh).props("flat round dense color=grey-7") \
                .tooltip("Look for ports again")

        connecting = state.connection == "connecting"
        ui.button("Connecting ..." if connecting else "Connect", icon="power", on_click=self.connect) \
            .props(f"unelevated color=primary {'loading' if connecting else ''}") \
            .classes("w-full sl-btn-main")

    async def connect(self) -> None:
        """Connect to the chosen port (in a worker thread, so the page stays responsive)."""
        port = self.port_select.value if self.port_select else None
        if not port:
            ui.notify("Choose a port first (or the simulator).", type="warning")
            return
        self.state.connection = "connecting"
        self.connection_block.refresh()
        try:
            await run.io_bound(self.state.connect, port)
        except ServoLabError as error:
            ui.notify(str(error), type="negative", multi_line=True, timeout=8000)
        except Exception as error:  # e.g. permission denied on Linux
            self.state.connection = "disconnected"
            ui.notify(f"Could not connect: {error}", type="negative", multi_line=True, timeout=8000)
        else:
            count = len(self.state.device_ids)
            ui.notify(f"Connected. {found_text(self.state)}.", type="positive" if count else "warning")
        self.on_connection_change()

    def disconnect(self) -> None:
        """Switch all motors off and close the port."""
        self.state.disconnect()
        ui.notify("Disconnected. All motors were switched off.")
        self.on_connection_change()

    async def rescan(self) -> None:
        """Look for devices on the bus again."""
        notification = ui.notification("Scanning the bus ...", spinner=True, timeout=None)
        try:
            await run.io_bound(self.state.rescan)
        except ServoLabError as error:
            ui.notify(str(error), type="negative")
        finally:
            notification.dismiss()
        self.on_connection_change()

    def torque_off_all(self) -> None:
        """Emergency button: switch every motor off."""
        if self.state.bus is None:
            ui.notify("Not connected.")
            return
        try:
            self.state.bus.torque_off_all()
        except ServoLabError as error:
            ui.notify(str(error), type="negative")
            return
        ui.notify("All motors switched off.", type="warning", icon="power_settings_new")
        self.on_navigate()

    # ------------------------------------------------------------------
    # Device list: motors, then sensors (IMUs)
    # ------------------------------------------------------------------

    @ui.refreshable_method
    def device_list(self) -> None:
        """List of motors, then sensors, each with a status dot and a live value."""
        state = self.state
        self.device_widgets = {}
        self.list_heading("Motors", state.motor_ids)

        if state.connection != "connected":
            ui.label("Connect to see your motors.").classes("sl-hint px-1 py-2")
            return
        if not state.device_ids:
            ui.label("No motors or sensors found. Check power and cables, then scan again.") \
                .classes("sl-hint px-1 py-2")
            return
        if not state.motor_ids:
            ui.label("No motors found.").classes("sl-hint px-1 py-2")

        for motor_id in state.motor_ids:
            self.device_item(motor_id, state.bus.motors[motor_id].model, "motor")
        if state.sensor_ids:
            with ui.element("div").classes("w-full pt-3"):
                self.list_heading("Sensors", state.sensor_ids)
            for sensor_id in state.sensor_ids:
                self.device_item(sensor_id, state.bus.sensors[sensor_id].model, "sensor")

    def list_heading(self, title: str, ids: list[int]) -> None:
        """Small heading of the device list, with the number of devices."""
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(title).classes("sl-side-label")
            if ids:
                ui.label(str(len(ids))).classes("sl-count")

    def device_item(self, device_id: int, model: str, kind: str) -> None:
        """One clickable entry of the device list."""
        selected = self.state.view == kind and device_id == self.state.selected_id
        item = ui.element("div").classes("sl-device" + (" sl-device-selected" if selected else ""))
        item.on("click", lambda _: self.select_device(device_id, kind))
        with item:
            dot = ui.element("div").classes("sl-dot sl-dot-ok")
            with ui.column().classes("gap-0 grow min-w-0"):
                ui.label(f"ID {device_id}").classes("sl-device-name")
                ui.label(model).classes("text-xs sl-muted leading-tight")
            value = ui.label("").classes("text-xs sl-muted sl-mono")
        self.device_widgets[device_id] = {"item": item, "dot": dot, "value": value, "kind": kind}

    def select_device(self, device_id: int, kind: str) -> None:
        """Show this device in the main area."""
        self.state.selected_id = device_id
        self.state.view = kind
        self.device_list.refresh()
        self.nav_block.refresh()
        self.on_navigate()

    def update_live(self) -> None:
        """Called by the page timer: update dots and values without rebuilding."""
        for device_id, widgets in self.device_widgets.items():
            if widgets["kind"] == "sensor":
                live = self.state.sensor_live.get(device_id)
                if live is None:
                    continue
                if not live.online:
                    css, text = "sl-dot sl-dot-off", "offline"
                else:
                    css, text = "sl-dot sl-dot-ok", f"|a| {math.hypot(*live.acceleration):.2f}"
            else:
                live = self.state.live.get(device_id)
                if live is None:
                    continue
                if not live.online:
                    css, text = "sl-dot sl-dot-off", "offline"
                elif live.status:
                    css, text = "sl-dot sl-dot-warn", ", ".join(live.status)
                else:
                    css, text = "sl-dot sl-dot-ok", f"{live.position:+.2f} rad"
            widgets["dot"].classes(replace=css)
            widgets["value"].set_text(text)
            if widgets.get("online") != live.online:   # offline devices are hatched
                widgets["online"] = live.online
                if live.online:
                    widgets["item"].classes(remove="sl-device-off")
                else:
                    widgets["item"].classes(add="sl-device-off")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    @ui.refreshable_method
    def nav_block(self) -> None:
        """The link to the documentation."""
        selected = self.state.view == "docs"
        item = ui.element("div").classes("sl-nav" + (" sl-nav-selected" if selected else ""))
        item.on("click", self.open_docs)
        with item:
            ui.icon("menu_book", size="20px")
            ui.label("Documentation")

    def open_docs(self) -> None:
        """Show the documentation in the main area."""
        self.state.view = "docs"
        self.device_list.refresh()
        self.nav_block.refresh()
        self.on_navigate()


def simulated_robots() -> list[str]:
    """Robot models that can be simulated (only if MuJoCo is installed)."""
    try:
        import mujoco  # noqa: F401
    except ImportError:
        return []
    from servolab.ports.mujoco_port import ROBOTS_DIR
    return sorted(p.name for p in ROBOTS_DIR.iterdir() if (p / "scene.xml").is_file())


def found_text(state: ScopeState) -> str:
    """Short summary for the connection box, e.g. "3 motor(s), 1 sensor(s) found"."""
    text = f"{len(state.motor_ids)} motor(s)"
    if state.sensor_ids:
        text += f", {len(state.sensor_ids)} sensor(s)"
    return text + " found"


def port_label(port_name: str) -> str:
    """Short name of a port for the connection box, e.g. "Simulator"."""
    if port_name == SIM_PORT:
        return "Simulator"
    if port_name.startswith("sim:"):
        return f"Simulated {port_name[len('sim:'):].upper()}"
    return port_name
