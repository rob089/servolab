"""
ServoScope main page for one motor: info, control, monitor, PID tuning, settings.
"""

from __future__ import annotations

import io
import math
import time
from typing import Callable

from nicegui import run, ui

import servolab
from servolab.errors import ServoLabError
from servolab.scope import doodles, theme
from servolab.scope.register_editor import RegisterEditor
from servolab.scope.state import ScopeState

SIGNALS = {
    "position": ("Position", "rad"),
    "velocity": ("Velocity", "rad/s"),
    "current": ("Current", "A"),
    "load": ("Load", "-1 … 1"),
}
MODE_LABELS = {"position": "Position", "velocity": "Velocity", "pwm": "PWM"}
LOW_SUPPLY_VOLTS = 6.0   # warn below this (STS3215 7.4 V version)
STEP_COLORS = [theme.INK, theme.WARN, theme.OK, theme.BAD, theme.INK_3]   # blue is the goal


def notify_error(error: Exception) -> None:
    """Show a servolab error as a red notification."""
    ui.notify(str(error), type="negative", multi_line=True, timeout=6000)


class MotorView:
    """The main area for one motor. Rebuilt whenever another motor is selected."""
    def __init__(self, state: ScopeState, on_motors_changed: Callable[[], None]):
        self.state = state
        self.on_motors_changed = on_motors_changed
        self.signal = "position"
        self.window = 10
        self.step_runs: list[dict] = []
        self.step_direction = 1
        self.settings = RegisterEditor(state, get_device=state.motor, on_changed=on_motors_changed,
                                       open_groups=("identity", "control"),
                                       rebuild_after=("operating_mode", "torque_enable"))
        self.live_labels: dict[str, ui.label] = {}
        self.chart: ui.echart | None = None
        self.step_chart: ui.echart | None = None
        self.motor_id: int | None = None

    # ==================================================================
    # Page
    # ==================================================================

    def build(self) -> None:
        """Build the page of the selected motor, or an empty state if there is none."""
        motor = self.state.motor()
        self.motor_id = motor.id if motor else None
        self.live_labels = {}
        self.chart = None
        self.step_chart = None
        if motor is None:
            self.empty_state()
            return
        self.step_runs = []

        self.header(motor)
        with ui.element("div").classes("grid w-full gap-6 grid-cols-1 xl:grid-cols-[400px_minmax(0,1fr)]"):
            self.control_card(motor)
            self.monitor_card()
        self.pid_card(motor)
        self.settings.card()

    def empty_state(self) -> None:
        """Drawing and hint when there is no connection or no device on the bus."""
        connected = self.state.connection == "connected"
        with ui.element("div").classes("sl-empty w-full mt-2"):
            ui.html(doodles.no_motors() if connected else doodles.not_connected(), sanitize=False)  # our own SVG
            with ui.column().classes("gap-3"):
                if connected:
                    ui.label("No device found").classes("sl-h2")
                    ui.label("The adapter is connected, but nothing on the bus answers: no motor and no "
                             "sensor. Check that they have power (6-7.4 V) and that the cable sits in the "
                             "adapter, then press the scan button in the sidebar.") \
                        .classes("text-[15px] text-[var(--sl-ink-2)] max-w-xl")
                else:
                    ui.label("Not connected").classes("sl-h2")
                    ui.label("Plug the adapter into your computer, choose its port in the sidebar "
                             "(or the simulator) and press Connect.") \
                        .classes("text-[15px] text-[var(--sl-ink-2)] max-w-xl")

    # ==================================================================
    # Header / device info
    # ==================================================================

    def header(self, motor: servolab.Motor) -> None:
        """Title, ID, firmware, port and live supply and temperature chips."""
        try:
            firmware = f"{motor.read_register('firmware_major')}.{motor.read_register('firmware_minor')}"
        except ServoLabError:
            firmware = "?"
        left, right = theme.page_head(f"Motor · {motor.model}", f"Motor {motor.id}")
        with left:
            with ui.element("div").classes("sl-metarow"):
                ui.html(f"<span>ID <b>{motor.id}</b></span>")
                ui.html(f"<span>Firmware <b>{firmware}</b></span>")
                ui.html(f"<span>Port <b>{self.state.port_name}</b></span>")
                self.live_labels["voltage_chip"] = ui.html("<span>Supply <b>–</b></span>")
                self.live_labels["temp_chip"] = ui.html("<span>Temp <b>–</b></span>")
        with right:
            self.status_chips()

    @ui.refreshable_method
    def status_chips(self) -> None:
        """Mode and status pills in the header (refreshed by the page timer)."""
        motor = self.state.motor()
        if motor is None:
            return
        live = self.state.live.get(motor.id)
        mode = MODE_LABELS.get(motor.mode, str(motor.mode))
        ui.html(theme.pill(f"{mode} mode", "accent"))
        if live is not None and not live.online:
            ui.html(theme.pill("● offline", "bad"))
        elif live is not None and live.status:
            ui.html(theme.pill(f"⚠ {', '.join(live.status)}", "warn"))
        else:
            ui.html(theme.pill("✓ OK", "ok"))

    # ==================================================================
    # Control
    # ==================================================================

    def control_card(self, motor: servolab.Motor) -> None:
        """Torque switch, mode toggle, the goal controls of the current mode and live values."""
        try:
            torque = motor.torque_enabled
        except ServoLabError as error:
            notify_error(error)
            torque = False

        with theme.card():
            ui.label("Control").classes("sl-card-title")

            with ui.row().classes("w-full items-center justify-between no-wrap"):
                with ui.column().classes("gap-0"):
                    ui.label("Torque").classes("sl-label")
                    self.torque_hint = ui.label("").classes("sl-hint")
                self.torque_switch = ui.switch(value=torque, on_change=self.set_torque).props("color=primary size=lg")
            self.update_torque_hint(torque)

            ui.label("Mode").classes("sl-label -mb-2")
            current_mode = motor.mode if motor.mode in MODE_LABELS else None
            ui.toggle(MODE_LABELS, value=current_mode, on_change=self.set_mode) \
                .props(f"spread {theme.TOGGLE_PROPS}").classes("w-full sl-seg")

            with ui.column().classes("w-full gap-2"):
                self.command_area()

            with ui.element("div").classes("grid grid-cols-2 gap-3 w-full mt-1"):
                for key, (label, unit) in SIGNALS.items():
                    with ui.element("div").classes("sl-tile"):
                        ui.label(label).classes("sl-stat-label")
                        with ui.row().classes("items-baseline gap-0 no-wrap"):
                            self.live_labels[key] = ui.label("–").classes("sl-stat-value")
                            ui.label(unit).classes("sl-stat-unit")
                        if key == "position":
                            self.live_labels["position_deg"] = ui.label("").classes("sl-hint sl-mono")

            ui.button("Set current position as zero", icon="my_location", on_click=self.confirm_set_zero) \
                .props("outline color=dark no-caps").classes("self-start")

    def update_torque_hint(self, torque: bool) -> None:
        """Text under the torque switch."""
        self.torque_hint.set_text("Motor is powered and holds / moves" if torque else "Motor is free – turn it by hand")

    @ui.refreshable_method
    def command_area(self) -> None:
        """Slider and buttons for the goal of the current mode, locked while torque is off."""
        motor = self.state.motor()
        if motor is None:
            return
        mode = motor.mode
        controls = []   # everything that moves the motor: locked while torque is off
        if mode == "position":
            ui.label("Goal position").classes("sl-label")
            goal = self.state.goal.get(motor.id)
            if goal is None:
                goal = round(self.state.live[motor.id].position, 2) if motor.id in self.state.live else 0.0
            slider = ui.slider(min=-math.pi, max=math.pi, step=0.01, value=goal,
                               on_change=lambda e: self.send_goal(e.value)).props("label color=dark")
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                number = ui.number(value=goal, min=-math.pi, max=math.pi, step=0.05, format="%.2f", suffix="rad") \
                    .props("outlined dense").classes("w-36")
                number.on("keydown.enter", lambda: slider.set_value(number.value))
                ui.space()
                for label, value in (("−90°", -math.pi / 2), ("0", 0.0), ("+90°", math.pi / 2)):
                    controls.append(ui.button(label, on_click=lambda v=value: slider.set_value(v))
                                    .props("outline dense no-caps color=dark").classes("px-3"))
            slider.on_value_change(lambda e: number.set_value(round(e.value, 2)))
            controls += [slider, number]
        elif mode == "velocity":
            ui.label("Goal velocity").classes("sl-label")
            slider = ui.slider(min=-6.0, max=6.0, step=0.05, value=0.0,
                               on_change=lambda e: self.send_velocity(e.value)).props("label color=dark")
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("rad/s").classes("sl-hint sl-mono")
                stop = ui.button("Stop", icon="stop", on_click=lambda: slider.set_value(0.0)) \
                    .props("outline dense no-caps color=dark").classes("px-3")
            controls += [slider, stop]
        elif mode == "pwm":
            ui.label("PWM output").classes("sl-label")
            slider = ui.slider(min=-1.0, max=1.0, step=0.01, value=0.0,
                               on_change=lambda e: self.send_pwm(e.value)).props("label color=dark")
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("No controller in the motor – it keeps turning!").classes("sl-hint sl-text-warn")
                stop = ui.button("Stop", icon="stop", on_click=lambda: slider.set_value(0.0)) \
                    .props("outline dense no-caps color=dark").classes("px-3")
            controls += [slider, stop]
        else:
            ui.label(f"Mode '{mode}' is not supported in ServoScope yet.").classes("sl-muted text-sm")

        if controls and not self.torque_switch.value:
            for control in controls:
                control.disable()
            ui.label("Switch torque on to move the motor.").classes("sl-hint")

    # -- actions -------------------------------------------------------

    def set_torque(self, event) -> None:
        """Torque switch changed: switch the motor on or off."""
        motor = self.state.motor()
        if motor is None:
            return
        try:
            motor.torque_enabled = event.value
        except ServoLabError as error:
            notify_error(error)
            return
        # Torque on: hold where the motor is now. Torque off: forget the goal.
        on = event.value and motor.mode == "position"
        self.state.goal[motor.id] = self.state.live[motor.id].position if on else None
        self.command_area.refresh()      # unlocks / locks the controls
        self.update_torque_hint(event.value)

    def set_mode(self, event) -> None:
        """Mode toggle changed: switch the motor's operating mode."""
        motor = self.state.motor()
        if motor is None or event.value is None or event.value == motor.mode:
            return
        try:
            motor.mode = event.value
        except ServoLabError as error:
            notify_error(error)
            return
        self.state.goal[motor.id] = None
        self.command_area.refresh()
        self.status_chips.refresh()

    def send_goal(self, rad: float) -> None:
        """Position slider moved: send the new goal (rad)."""
        motor = self.state.motor()
        if motor is None:
            return
        try:
            motor.position = rad
            self.state.goal[motor.id] = rad
        except ServoLabError as error:
            notify_error(error)

    def send_velocity(self, rad_per_s: float) -> None:
        """Velocity slider moved: send the new speed (rad/s)."""
        motor = self.state.motor()
        try:
            motor.velocity = rad_per_s
        except ServoLabError as error:
            notify_error(error)

    def send_pwm(self, fraction: float) -> None:
        """PWM slider moved: send the new PWM (-1 ... 1)."""
        motor = self.state.motor()
        try:
            motor.pwm = fraction
        except ServoLabError as error:
            notify_error(error)

    def confirm_set_zero(self) -> None:
        """Ask before set_zero(), because it writes the EEPROM and switches torque off."""
        with ui.dialog() as dialog, ui.card().classes("p-6 gap-4 max-w-md"):
            ui.label("Set zero here?").classes("sl-h2")
            ui.label("The current position becomes 0 rad. This is saved in the motor (EEPROM). "
                     "Torque is switched off for this.").classes("sl-muted")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("outline color=dark")
                ui.button("Set zero", on_click=lambda: (dialog.close(), self.set_zero())).props("unelevated color=primary")
        dialog.open()

    def set_zero(self) -> None:
        """Make the current position the motor's new zero."""
        motor = self.state.motor()
        try:
            motor.set_zero()
        except ServoLabError as error:
            notify_error(error)
            return
        self.torque_switch.set_value(False)
        self.state.goal[motor.id] = None
        self.command_area.refresh()
        ui.notify("Zero set. Torque is off.", type="positive")

    # ==================================================================
    # Monitor
    # ==================================================================

    def monitor_card(self) -> None:
        """Live plot of one signal, with window length, pause and CSV download."""
        with theme.card():
            with ui.row().classes("w-full items-center justify-between gap-3"):
                ui.label("Monitor").classes("sl-card-title")
                with ui.row().classes("items-center gap-2"):
                    ui.toggle({key: label for key, (label, _) in SIGNALS.items()}, value=self.signal,
                              on_change=self.set_signal) \
                        .props(f"dense {theme.TOGGLE_PROPS}").classes("sl-seg sl-seg-sm")
                    ui.select({5: "5 s", 10: "10 s", 30: "30 s"}, value=self.window,
                              on_change=lambda e: setattr(self, "window", e.value)) \
                        .props("outlined dense options-dense").classes("w-24")
                    self.pause_button = ui.button(icon="pause", on_click=self.toggle_pause) \
                        .props("outline round dense color=dark").tooltip("Pause / resume recording")
                    ui.button(icon="download", on_click=self.download_csv) \
                        .props("outline round dense color=dark").tooltip("Download the recording as CSV")
            self.chart = ui.echart(self.chart_options()).classes("w-full grow min-h-[340px]")
            self.chart_caption = ui.label("").classes("sl-hint -mt-2")
            self.update_pause_icon()

    def chart_options(self) -> dict:
        """ECharts options for the monitor plot of the chosen signal (position also shows the goal)."""
        label, unit = SIGNALS[self.signal]
        series = [{
            "name": label, "type": "line", "showSymbol": False, "data": [],
            "lineStyle": {"width": 1.8, "color": theme.PLOT_MAIN}, "itemStyle": {"color": theme.PLOT_MAIN},
            "areaStyle": {"color": "rgba(23,22,20,0.06)"},
        }]
        if self.signal == "position":
            series.append({
                "name": "Goal", "type": "line", "showSymbol": False, "data": [], "step": "end",
                "lineStyle": {"width": 1.6, "type": [5, 4], "color": theme.PLOT_GOAL},
                "itemStyle": {"color": theme.PLOT_GOAL},
            })
        return {
            "animation": False,
            "textStyle": theme.CHART_TEXT,
            "grid": {"left": 56, "right": 16, "top": 28, "bottom": 44},
            "legend": {"show": self.signal == "position", "right": 0, "top": 0, "icon": "roundRect",
                       "itemWidth": 14, "itemHeight": 3, "textStyle": theme.CHART_TEXT},
            "tooltip": theme.CHART_TOOLTIP,
            "xAxis": {"type": "value", "name": "time [s]", "nameLocation": "middle", "nameGap": 28,
                      "nameTextStyle": theme.CHART_TEXT,
                      "axisLine": {"lineStyle": {"color": theme.INK}}, "axisLabel": theme.CHART_AXIS_LABEL,
                      "splitLine": {"lineStyle": {"color": theme.PLOT_GRID}}},
            "yAxis": {"type": "value", "name": f"{label} [{unit}]", "nameTextStyle": {**theme.CHART_TEXT, "align": "left"},
                      "scale": True, "axisLabel": theme.CHART_AXIS_LABEL,
                      "splitLine": {"lineStyle": {"color": theme.PLOT_GRID}}},
            "series": series,
        }

    def set_signal(self, event) -> None:
        """Another signal was chosen: rebuild the plot for it."""
        self.signal = event.value
        if self.chart is not None:
            self.chart.options.clear()
            self.chart.options.update(self.chart_options())
            self.update_chart()

    def toggle_pause(self) -> None:
        """Pause or resume recording. The plots of all devices freeze while paused."""
        self.state.paused = not self.state.paused
        self.update_pause_icon()

    def update_pause_icon(self) -> None:
        """Pause icon while recording, play icon while paused."""
        self.pause_button.props(f"icon={'play_arrow' if self.state.paused else 'pause'}")

    def update_chart(self) -> None:
        """Put the last `window` seconds of the history into the monitor plot."""
        motor_id = self.motor_id
        history = self.state.history.get(motor_id)
        if self.chart is None or history is None or not history.t:
            return
        times = list(history.t)
        end = times[-1]
        start = end - self.window
        first = 0
        for i in range(len(times) - 1, -1, -1):
            if times[i] < start:
                first = i + 1
                break
        values = list(getattr(history, self.signal))[first:]
        times = times[first:]
        options = self.chart.options
        options["series"][0]["data"] = [[round(t, 3), round(v, 4)] for t, v in zip(times, values)]
        if self.signal == "position":
            goals = list(history.goal)[first:]
            options["series"][1]["data"] = [[round(t, 3), None if g is None else round(g, 4)]
                                            for t, g in zip(times, goals)]
        options["xAxis"]["min"] = round(max(start, times[0]), 2)
        options["xAxis"]["max"] = round(end, 2)
        self.chart.update()
        paused = " · paused" if self.state.paused else ""
        self.chart_caption.set_text(f"Recording at {self.state.loop_hz:.0f} Hz{paused}")

    def download_csv(self) -> None:
        """Download the recorded history of this motor as a CSV file."""
        history = self.state.history.get(self.motor_id)
        if history is None or not history.t:
            ui.notify("Nothing recorded yet.")
            return
        out = io.StringIO()
        out.write("time_s,position_rad,velocity_rad_s,current_A,load,goal_rad\n")
        for row in zip(history.t, history.position, history.velocity, history.current, history.load, history.goal):
            out.write(",".join("" if v is None else f"{v:.6g}" for v in row) + "\n")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        ui.download.content(out.getvalue(), f"servoscope_motor{self.motor_id}_{stamp}.csv", "text/csv")

    # ==================================================================
    # PID
    # ==================================================================

    def pid_card(self, motor: servolab.Motor) -> None:
        """Gains of the motor's position controller, and the step test to compare them."""
        try:
            p, i, d = motor.pid
        except ServoLabError:
            p, i, d = 0, 0, 0
        with theme.card():
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("PID tuning").classes("sl-card-title")
                ui.label("Gains of the controller inside the motor (position mode). Changes are live, "
                         "not saved after power-off.").classes("sl-hint")
            with ui.element("div").classes("grid w-full gap-6 grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)]"):
                with ui.column().classes("gap-3"):
                    with ui.row().classes("gap-2 no-wrap"):
                        self.p_input = ui.number("P", value=p, min=0, max=254, step=1, format="%d").props("outlined dense").classes("w-20")
                        self.i_input = ui.number("I", value=i, min=0, max=254, step=1, format="%d").props("outlined dense").classes("w-20")
                        self.d_input = ui.number("D", value=d, min=0, max=254, step=1, format="%d").props("outlined dense").classes("w-20")
                    ui.button("Apply gains", icon="check", on_click=self.apply_pid).props("outline color=dark").classes("w-full")
                    ui.separator().classes("my-1")
                    ui.label("Step test").classes("sl-h3")
                    ui.label("Moves the motor by the step size and records the response. "
                             "Needs position mode and torque on.").classes("sl-hint -mt-2")
                    with ui.row().classes("gap-2 no-wrap"):
                        self.step_size = ui.number("Step", value=0.5, min=0.05, max=2.0, step=0.05, suffix="rad") \
                            .props("outlined dense").classes("w-32")
                        self.step_duration = ui.number("Duration", value=1.5, min=0.3, max=5.0, step=0.1, suffix="s") \
                            .props("outlined dense").classes("w-32")
                    with ui.row().classes("w-full gap-2 no-wrap"):
                        self.step_button = ui.button("Run step test", icon="play_arrow", on_click=self.run_step_test) \
                            .props("unelevated color=primary").classes("grow")
                        ui.button(icon="delete_sweep", on_click=self.clear_steps).props("outline round color=dark") \
                            .tooltip("Clear all runs")
                self.step_chart = ui.echart(self.step_chart_options()).classes("w-full h-[300px]")

    async def apply_pid(self) -> None:
        """Send the gains from the three input fields to the motor."""
        motor = self.state.motor()
        try:
            motor.pid = (int(self.p_input.value or 0), int(self.i_input.value or 0), int(self.d_input.value or 0))
        except (ServoLabError, ValueError) as error:
            notify_error(error)
            return
        ui.notify(f"Gains applied: P={motor.pid[0]}, I={motor.pid[1]}, D={motor.pid[2]}", type="positive")
        await self.settings.load_registers()   # keep the settings section in sync

    def step_chart_options(self) -> dict:
        """ECharts options for the step test plot: the goal and up to six runs."""
        series = [{"name": "Goal", "type": "line", "showSymbol": False, "data": [[0, 0], [0, 1], [10, 1]],
                   "lineStyle": {"type": [5, 4], "color": theme.PLOT_GOAL, "width": 1.4}, "itemStyle": {"color": theme.PLOT_GOAL}}]
        for index, run_data in enumerate(self.step_runs):
            color = STEP_COLORS[index % len(STEP_COLORS)]
            series.append({"name": run_data["label"], "type": "line", "showSymbol": False, "data": run_data["data"],
                           "lineStyle": {"width": 1.8, "color": color}, "itemStyle": {"color": color}})
        duration = max((r["duration"] for r in self.step_runs), default=1.5)
        return {
            "animation": False,
            "textStyle": theme.CHART_TEXT,
            "grid": {"left": 48, "right": 16, "top": 36, "bottom": 44},
            "legend": {"top": 0, "right": 0, "icon": "roundRect", "itemWidth": 14, "itemHeight": 3,
                       "textStyle": theme.CHART_TEXT},
            "tooltip": theme.CHART_TOOLTIP,
            "xAxis": {"type": "value", "min": -0.1, "max": round(duration, 2), "name": "time after step [s]",
                      "nameLocation": "middle", "nameGap": 28, "nameTextStyle": theme.CHART_TEXT,
                      "axisLine": {"lineStyle": {"color": theme.INK}}, "axisLabel": theme.CHART_AXIS_LABEL,
                      "splitLine": {"lineStyle": {"color": theme.PLOT_GRID}}},
            "yAxis": {"type": "value", "name": "response (1 = goal)", "nameTextStyle": {**theme.CHART_TEXT, "align": "left"},
                      "axisLabel": theme.CHART_AXIS_LABEL, "splitLine": {"lineStyle": {"color": theme.PLOT_GRID}}},
            "series": series,
        }

    def refresh_step_chart(self) -> None:
        """Redraw the step test plot after a new run or after clearing."""
        if self.step_chart is None:
            return
        self.step_chart.options.clear()
        self.step_chart.options.update(self.step_chart_options())
        self.step_chart.update()

    async def run_step_test(self) -> None:
        """Run one step (alternately up and down) in a worker thread and add it to the plot."""
        motor = self.state.motor()
        if motor is None:
            return
        if motor.mode != "position":
            ui.notify("Switch to position mode first.", type="warning")
            return
        if not self.torque_switch.value:
            ui.notify("Switch torque on first.", type="warning")
            return
        size = float(self.step_size.value or 0.5)
        duration = float(self.step_duration.value or 1.5)
        self.step_button.props("loading")
        try:
            result = await run.io_bound(step_response, motor, size * self.step_direction, duration)
        except ServoLabError as error:
            notify_error(error)
            return
        finally:
            self.step_button.props(remove="loading")
        self.step_direction *= -1
        self.state.goal[motor.id] = result["goal"]
        p, i, d = motor.pid
        self.step_runs.append({"label": f"P{p} I{i} D{d}", "data": result["data"], "duration": duration})
        self.step_runs = self.step_runs[-6:]
        self.refresh_step_chart()
        self.command_area.refresh()

    def clear_steps(self) -> None:
        """Remove all step test runs from the plot."""
        self.step_runs = []
        self.refresh_step_chart()

    # ==================================================================
    # Live update (called by the page timer)
    # ==================================================================

    def update_live(self) -> None:
        """Page timer: update the live values, the header chips and the monitor plot."""
        live = self.state.live.get(self.motor_id) if self.motor_id is not None else None
        if live is None or not self.live_labels:
            return
        labels = self.live_labels
        labels["position"].set_text(f"{live.position:+.3f}")
        labels["velocity"].set_text(f"{live.velocity:+.2f}")
        labels["current"].set_text(f"{live.current:.3f}")
        labels["load"].set_text(f"{live.load:+.2f}")
        labels["position_deg"].set_text(f"= {math.degrees(live.position):+.1f}°")
        if live.voltage < LOW_SUPPLY_VOLTS:
            labels["voltage_chip"].set_content(
                f'<span class="warn" title="Below {LOW_SUPPLY_VOLTS} V the motor is weak '
                f'and may restart during fast moves. Use a 6-7.4 V supply.">'
                f'⚠ Supply <b>{live.voltage:.1f} V</b> low</span>')
        else:
            labels["voltage_chip"].set_content(f"<span>Supply <b>{live.voltage:.1f} V</b></span>")
        temp_class = ' class="warn"' if live.temperature >= 55 else ""
        labels["temp_chip"].set_content(f"<span{temp_class}>Temp <b>{live.temperature:.0f} °C</b></span>")
        self.update_chart()


# ----------------------------------------------------------------------
# Blocking helpers (run in a worker thread via run.io_bound)
# ----------------------------------------------------------------------

def step_response(motor: servolab.Motor, size: float, duration: float) -> dict:
    """Step the goal by `size` rad and record the normalised response."""
    start = motor.position
    goal = start + size
    if abs(goal) > math.pi - 0.05:   # stay inside the single-turn range
        goal = start - size
    span = goal - start
    data = []
    t0 = time.perf_counter()
    while (now := time.perf_counter() - t0) < 0.1:          # short baseline before the step
        data.append([round(now - 0.1, 4), round((motor.position - start) / span, 4)])
        time.sleep(0.004)
    motor.position = goal
    t_step = time.perf_counter()
    while (now := time.perf_counter() - t_step) < duration:
        data.append([round(now, 4), round((motor.position - start) / span, 4)])
        time.sleep(0.004)
    return {"goal": goal, "data": data}
