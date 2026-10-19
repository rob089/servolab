"""
ServoScope settings card: every register of one device (motor or IMU), generated
from the register table in servolab/registers.py. Used by MotorView and ImuView.
"""

from __future__ import annotations

from typing import Callable

from nicegui import run, ui

import servolab
from servolab.errors import ServoLabError
from servolab.registers import REGISTER_TABLES
from servolab.scope import theme
from servolab.scope.state import ScopeState

GROUP_TITLES = {
    "identity": ("Identity", "badge"),
    "control": ("Internal controller", "tune"),
    "settings": ("Measurement settings", "tune"),
    "limits": ("Limits", "straighten"),
    "protection": ("Protection", "shield"),
    "command": ("Commands (live)", "send"),
    "state": ("State (read only)", "monitor_heart"),
    "factory": ("Factory settings – change with care", "factory"),
}


def notify_error(error: Exception) -> None:
    """Show a servolab error as a red notification."""
    ui.notify(str(error), type="negative", multi_line=True, timeout=6000)


class RegisterEditor:
    """The "Settings" card for the device returned by `get_device`."""

    def __init__(self, state: ScopeState, get_device: Callable, on_changed: Callable[[], None],
                 open_groups: tuple[str, ...], rebuild_after: tuple[str, ...] = ()):
        self.state = state
        self.get_device = get_device          # () -> Motor / Imu / None
        self.on_changed = on_changed          # rebuild the page (devices or modes changed)
        self.open_groups = open_groups        # groups that start expanded
        self.rebuild_after = rebuild_after    # register names whose change needs a page rebuild
        self.values: dict[str, int] = {}

    def card(self) -> None:
        """Build the card; the register values are read right after (see load_registers())."""
        self.values = {}
        with theme.card():
            with ui.row().classes("w-full items-center justify-between gap-3"):
                ui.label("Settings").classes("sl-card-title")
                with ui.row().classes("gap-2"):
                    ui.button("Factory reset", icon="restart_alt", on_click=self.confirm_factory_reset) \
                        .props("outline no-caps color=negative")
                    ui.button("Reload", icon="refresh", on_click=self.load_registers).props("outline no-caps color=dark")
                    ui.button("Save to EEPROM", icon="save", on_click=self.save_eeprom).props("unelevated no-caps color=primary")
            with ui.row().classes("sl-note w-full items-start gap-3 no-wrap"):
                ui.icon("info", size="20px").classes("mt-px")
                ui.label("Changes are active immediately but lost after power-off. Press “Save to EEPROM” "
                         "to keep them. Values are raw register values – see the unit column. "
                         "Press Enter to write a value.")
            with ui.column().classes("w-full gap-2"):
                self.register_groups()
        ui.timer(0.05, self.load_registers, once=True)

    @ui.refreshable_method
    def register_groups(self) -> None:
        """One expandable section per register group (see GROUP_TITLES)."""
        device = self.get_device()
        if device is None or device.model not in REGISTER_TABLES:
            return
        if not self.values:
            with ui.row().classes("items-center gap-2 py-4"):
                ui.spinner(size="sm")
                ui.label("Reading registers …").classes("sl-muted")
            return
        registers = REGISTER_TABLES[device.model]
        for group, (title, icon) in GROUP_TITLES.items():
            members = [r for r in registers if r.group == group]
            if not members:
                continue
            with ui.expansion(title, icon=icon, value=group in self.open_groups, caption=f"{len(members)} registers") \
                    .classes("w-full sl-expansion").props("dense"):
                with ui.column().classes("w-full gap-0 px-2 pb-2"):
                    for register in members:
                        self.register_row(register)

    def register_row(self, register) -> None:
        """Name, address, description, value (editable if writable) and unit of one register."""
        value = self.values.get(register.name)
        with ui.row().classes("sl-reg-row w-full items-center gap-4 no-wrap"):
            with ui.column().classes("gap-0 grow min-w-0"):
                with ui.row().classes("items-center gap-2"):
                    ui.label(register.name).classes("sl-mono text-[13px] font-semibold")
                    ui.label(f"@{register.address}").classes("text-[11px] sl-muted sl-mono")
                    if register.memory == "eeprom":
                        ui.label("EEPROM").classes("sl-tag-eeprom")
                ui.label(register.description).classes("sl-hint")
            if register.access == "rw":
                field = ui.number(value=value, step=1, format="%d").props("outlined dense input-class='text-right sl-mono'") \
                    .classes("w-28")
                field.on("keydown.enter", lambda _, r=register, f=field: self.write_register(r, f))
            else:
                ui.label("–" if value is None else str(value)).classes("w-28 text-right sl-mono pr-3")
            ui.label(register.unit).classes("w-24 sl-hint")

    async def load_registers(self) -> None:
        """Read every register of the device (in a worker thread) and show the values."""
        device = self.get_device()
        if device is None or device.model not in REGISTER_TABLES:
            return
        try:
            self.values = await run.io_bound(read_all_registers, device)
        except ServoLabError as error:
            notify_error(error)
            return
        self.register_groups.refresh()

    async def write_register(self, register, field: ui.number) -> None:
        """Enter pressed in a value field: write the register and show what the device now has."""
        device = self.get_device()
        if device is None or field.value is None:
            return
        value = int(field.value)
        if register.name == "id":
            await self.change_id(device, value)
            return
        try:
            device.write_register(register.name, value)
            self.values[register.name] = device.read_register(register.name)
        except ServoLabError as error:
            notify_error(error)
            field.set_value(self.values.get(register.name))
            return
        field.set_value(self.values[register.name])
        ui.notify(f"{register.name} = {value}", type="positive", position="bottom-right")
        if register.name in self.rebuild_after:
            self.on_changed()

    async def change_id(self, device, new_id: int) -> None:
        """Give the device a new ID (saved permanently) and scan the bus again."""
        if new_id in self.state.device_ids and new_id != device.id:
            ui.notify(f"ID {new_id} is already used by another device.", type="negative")
            return
        try:
            device.id = new_id                      # writes and saves the new ID
            await run.io_bound(self.state.rescan)
        except ServoLabError as error:
            notify_error(error)
            return
        self.state.selected_id = new_id
        ui.notify(f"Device now has ID {new_id} (saved).", type="positive")
        self.on_changed()

    async def save_eeprom(self) -> None:
        """Keep all current settings after power-off."""
        device = self.get_device()
        if device is None:
            return
        notification = ui.notification("Saving to EEPROM …", spinner=True, timeout=None)
        try:
            await run.io_bound(device.save_to_eeprom)
        except ServoLabError as error:
            notify_error(error)
            return
        finally:
            notification.dismiss()
        ui.notify("Settings saved in the device.", type="positive")

    def confirm_factory_reset(self) -> None:
        """Ask before a factory reset and explain what it does to this kind of device."""
        device = self.get_device()
        if device is None:
            return
        is_motor = isinstance(device, servolab.Motor)
        name = f"motor {device.id}" if is_motor else f"IMU {device.id}"
        if is_motor:
            text = (f"All settings of {name} go back to the values it came with from the factory: "
                    "limits, gains, mode, protection … The motor keeps its ID and its zero position. "
                    "This is saved in the motor (EEPROM).")
        else:
            text = (f"Ranges and sample rate of {name} go back to the factory values. "
                    "The IMU keeps its ID. This is saved in the IMU.")
        async def reset() -> None:
            """Dialog button: close the dialog, then reset."""
            dialog.close()
            await self.factory_reset()

        with ui.dialog() as dialog, ui.card().classes("p-6 gap-4 max-w-md"):
            ui.label("Restore factory settings?").classes("sl-h2")
            ui.label(text).classes("text-[var(--sl-ink-2)]")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("outline color=dark no-caps")
                ui.button("Factory reset", icon="restart_alt", on_click=reset) \
                    .props("unelevated color=negative no-caps")
        dialog.open()

    async def factory_reset(self) -> None:
        """Put the device back to its factory settings (in a worker thread)."""
        device = self.get_device()
        if device is None:
            return
        notification = ui.notification("Restoring factory settings …", spinner=True, timeout=None)
        try:
            await run.io_bound(device.factory_reset)
        except ServoLabError as error:
            notify_error(error)
            return
        finally:
            notification.dismiss()
        if device.id in self.state.goal:
            self.state.goal[device.id] = None      # the old goal means nothing now
        ui.notify("Factory settings restored.", type="positive")
        self.on_changed()                          # mode, torque, gains ... may have changed


def read_all_registers(device) -> dict[str, int]:
    """Blocking (run it via run.io_bound): raw value of every register of the device."""
    values = {}
    for register in REGISTER_TABLES[device.model]:
        values[register.name] = device.read_register(register.name)
    return values
