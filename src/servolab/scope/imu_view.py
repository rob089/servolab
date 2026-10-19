"""
ServoScope page for one IMU: info, live values, monitor, settings.
"""

from __future__ import annotations

import io
import math
import time
from typing import Callable

from nicegui import ui

import servolab
from servolab.errors import ServoLabError
from servolab.scope import theme
from servolab.scope.register_editor import RegisterEditor
from servolab.scope.state import ScopeState

# signal key -> (label, unit, component names)
SIGNALS = {
    "acceleration": ("Acceleration", "m/s²", ["x", "y", "z"]),
    "angular_velocity": ("Angular velocity", "rad/s", ["x", "y", "z"]),
}
SIGNAL_TOGGLE = {"acceleration": "Acceleration", "angular_velocity": "Angular velocity"}


class ImuView:
    """The main area for one IMU. Rebuilt whenever another device is selected."""
    def __init__(self, state: ScopeState, on_devices_changed: Callable[[], None]):
        self.state = state
        self.signal = "acceleration"
        self.window = 10
        self.live_labels: dict[str, ui.label] = {}
        self.chart: ui.echart | None = None
        self.sensor_id: int | None = None
        self.settings = RegisterEditor(state, get_device=state.sensor, on_changed=on_devices_changed,
                                       open_groups=("identity", "settings"))

    def build(self) -> None:
        """Build the page of the selected IMU (nothing if there is none)."""
        imu = self.state.sensor()
        self.sensor_id = imu.id if imu else None
        self.live_labels = {}
        self.chart = None
        if imu is None:
            return
        self.header(imu)
        with ui.element("div").classes("grid w-full gap-6 grid-cols-1 xl:grid-cols-[400px_minmax(0,1fr)]"):
            self.values_card()
            self.monitor_card()
        self.settings.card()

    # ==================================================================
    # Header / device info
    # ==================================================================

    def header(self, imu: servolab.Imu) -> None:
        """Title, ID, firmware, port, measuring ranges and the status chip."""
        try:
            info = imu.info
            firmware = info["firmware"]
            ranges = f"±{info['gyro_range']} °/s · ±{info['acc_range']} g · {info['sample_rate']} Hz"
        except ServoLabError:
            firmware, ranges = "?", "?"
        left, right = theme.page_head(f"Sensor · {imu.model}", f"IMU {imu.id}")
        with left:
            with ui.element("div").classes("sl-metarow"):
                ui.html(f"<span>ID <b>{imu.id}</b></span>")
                ui.html(f"<span>Firmware <b>{firmware}</b></span>")
                ui.html(f"<span>Port <b>{self.state.port_name}</b></span>")
                ui.html(f"<span>Ranges <b>{ranges}</b></span>")
        with right:
            self.live_labels["status_chip"] = ui.html("")

    # ==================================================================
    # Live values
    # ==================================================================

    def values_card(self) -> None:
        """Live acceleration and angular velocity, x / y / z, and the size of the acceleration."""
        with theme.card():
            ui.label("Live values").classes("sl-card-title")
            for key, (label, unit, components) in SIGNALS.items():
                with ui.column().classes("w-full gap-1"):
                    with ui.row().classes("items-baseline gap-2"):
                        ui.label(label).classes("sl-label")
                        if unit:
                            ui.label(unit).classes("sl-stat-unit")
                    with ui.element("div").classes("grid grid-cols-3 gap-2 w-full"):
                        for name in components:
                            with ui.element("div").classes("sl-tile"):
                                ui.label(name).classes("sl-stat-label")
                                self.live_labels[f"{key}_{name}"] = ui.label("–").classes("sl-stat-value")
            self.live_labels["norm"] = ui.label("").classes("sl-hint sl-mono")

    # ==================================================================
    # Monitor
    # ==================================================================

    def monitor_card(self) -> None:
        """Live plot of one signal (three axes), with window length, pause and CSV download."""
        with theme.card():
            with ui.row().classes("w-full items-center justify-between gap-3"):
                ui.label("Monitor").classes("sl-card-title")
                with ui.row().classes("items-center gap-2"):
                    ui.toggle(SIGNAL_TOGGLE, value=self.signal, on_change=self.set_signal) \
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
        """ECharts options for the monitor plot: one line per axis."""
        label, unit, components = SIGNALS[self.signal]
        series = []
        for i, name in enumerate(components):
            color = theme.PLOT_SERIES[i % len(theme.PLOT_SERIES)]
            series.append({"name": name, "type": "line", "showSymbol": False, "data": [],
                           "lineStyle": {"width": 1.6, "color": color}, "itemStyle": {"color": color}})
        y_name = f"{label} [{unit}]" if unit else label
        return {
            "animation": False,
            "textStyle": theme.CHART_TEXT,
            "grid": {"left": 56, "right": 16, "top": 28, "bottom": 44},
            "legend": {"show": True, "right": 0, "top": 0, "icon": "roundRect",
                       "itemWidth": 14, "itemHeight": 3, "textStyle": theme.CHART_TEXT},
            "tooltip": theme.CHART_TOOLTIP,
            "xAxis": {"type": "value", "name": "time [s]", "nameLocation": "middle", "nameGap": 28,
                      "nameTextStyle": theme.CHART_TEXT,
                      "axisLine": {"lineStyle": {"color": theme.INK}}, "axisLabel": theme.CHART_AXIS_LABEL,
                      "splitLine": {"lineStyle": {"color": theme.PLOT_GRID}}},
            "yAxis": {"type": "value", "name": y_name, "nameTextStyle": {**theme.CHART_TEXT, "align": "left"},
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
        history = self.state.sensor_history.get(self.sensor_id)
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
        times = times[first:]
        vectors = list(getattr(history, self.signal))[first:]
        options = self.chart.options
        for i, series in enumerate(options["series"]):
            series["data"] = [[round(t, 3), round(v[i], 4)] for t, v in zip(times, vectors)]
        options["xAxis"]["min"] = round(max(start, times[0]), 2)
        options["xAxis"]["max"] = round(end, 2)
        self.chart.update()
        paused = " · paused" if self.state.paused else ""
        self.chart_caption.set_text(f"Recording at {self.state.loop_hz:.0f} Hz{paused}")

    def download_csv(self) -> None:
        """Download the recorded history of this IMU as a CSV file."""
        history = self.state.sensor_history.get(self.sensor_id)
        if history is None or not history.t:
            ui.notify("Nothing recorded yet.")
            return
        out = io.StringIO()
        out.write("time_s,acc_x_m_s2,acc_y_m_s2,acc_z_m_s2,gyro_x_rad_s,gyro_y_rad_s,gyro_z_rad_s\n")
        for t, a, w in zip(history.t, history.acceleration, history.angular_velocity):
            out.write(",".join(f"{v:.6g}" for v in [t, *a, *w]) + "\n")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        ui.download.content(out.getvalue(), f"servoscope_imu{self.sensor_id}_{stamp}.csv", "text/csv")

    # ==================================================================
    # Live update (called by the page timer)
    # ==================================================================

    def update_live(self) -> None:
        """Page timer: update the live values, the status chip and the monitor plot."""
        live = self.state.sensor_live.get(self.sensor_id) if self.sensor_id is not None else None
        if live is None or not self.live_labels:
            return
        labels = self.live_labels
        for key, (_, _, components) in SIGNALS.items():
            values = getattr(live, key)
            for name, value in zip(components, values):
                labels[f"{key}_{name}"].set_text(f"{value:+.2f}")
        labels["norm"].set_text(f"|a| = {math.hypot(*live.acceleration):.2f} m/s²")
        if live.online:
            labels["status_chip"].set_content(theme.pill("✓ OK", "ok"))
        else:
            labels["status_chip"].set_content(theme.pill("● offline", "bad"))
        self.update_chart()
