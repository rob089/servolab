"""
ServoScope documentation view.

Everything here is generated from the servolab package itself, so it never goes
out of date:
- Guides: the Markdown files in servolab/docs/
- Python API: the docstrings of the public functions, classes and properties
- Registers: the table in servolab/registers.py
- Examples: the scripts in the examples/ folder (when available)
"""

from __future__ import annotations

import inspect
from pathlib import Path

from nicegui import ui

import servolab
from servolab.registers import STS3215_REGISTERS, XIAO_IMU_REGISTERS
from servolab.scope import theme
from servolab.scope.reference import (
    API,
    DOCS_DIR,
    GUIDES,
    api_entry,
    find_examples_dir,
    first_paragraph,
    toc_label,
)


class DocsView:
    """Every tab has the same layout: a table of contents on the left (it stays
    in view while scrolling) and the content in the full remaining width."""

    def build(self) -> None:
        """Build the tabs: Guides, Python API, Registers and (in a source checkout) Examples."""
        theme.page_head(f"Documentation · servolab {servolab.__version__}", "servolab & ServoScope")
        tab_names = ["Guides", "Python API", "Registers"]
        examples_dir = find_examples_dir()
        if examples_dir:
            tab_names.append("Examples")

        with ui.tabs().props("no-caps align=left dense") \
                .classes("w-full sl-tabs") as tabs:
            tab_objects = {name: ui.tab(name) for name in tab_names}
        with ui.tab_panels(tabs, value=tab_objects["Guides"]).classes("w-full bg-transparent sl-docs-panels") \
                .props("animated=false"):
            with ui.tab_panel(tab_objects["Guides"]).classes("p-0 pt-2"):
                self.guides()
            with ui.tab_panel(tab_objects["Python API"]).classes("p-0 pt-2"):
                self.api_reference()
            with ui.tab_panel(tab_objects["Registers"]).classes("p-0 pt-2"):
                self.registers()
            if examples_dir:
                with ui.tab_panel(tab_objects["Examples"]).classes("p-0 pt-2"):
                    self.examples(examples_dir)

    @staticmethod
    def layout() -> tuple[ui.column, ui.column]:
        """(toc, content): the two columns every tab uses."""
        with ui.element("div").classes("sl-docs-grid w-full"):
            with ui.column().classes("sl-toc gap-1") as toc:
                ui.label("Contents").classes("sl-kicker px-[14px] pb-2")
            content = ui.column().classes("gap-6 min-w-0 w-full")
        return toc, content

    # ------------------------------------------------------------------
    def guides(self) -> None:
        """The Markdown guides from servolab/docs/, one at a time, chosen in the table of contents."""
        toc, content = self.layout()
        with content:
            with theme.card().classes("sl-docs sl-prose"):
                markdown = ui.markdown("", extras=["fenced-code-blocks", "tables"])
        buttons = {}
        with toc:
            for filename, title in GUIDES:
                buttons[filename] = ui.element("div").classes("sl-nav")
                with buttons[filename]:
                    ui.label(title)

        def show(filename: str) -> None:
            """Show one guide and highlight it in the table of contents."""
            markdown.set_content((DOCS_DIR / filename).read_text(encoding="utf-8"))
            for name, element in buttons.items():
                element.classes(replace="sl-nav" + (" sl-nav-selected" if name == filename else ""))

        for filename, element in buttons.items():
            element.on("click", lambda _, f=filename: show(f))
        show(GUIDES[0][0])

    # ------------------------------------------------------------------
    def api_reference(self) -> None:
        """Signatures and docstrings of everything listed in API, grouped by class."""
        toc, content = self.layout()
        for heading, prefix, obj, members in API:
            with content:
                with theme.card().classes("sl-docs sl-anchor !gap-1") as section:
                    ui.label(heading).classes("sl-h2")
                    class_doc = inspect.getdoc(obj) if inspect.isclass(obj) else None
                    if class_doc:
                        ui.markdown(first_paragraph(class_doc)).classes("sl-muted")
                    entries = [self.api_entry(prefix, obj, member) for member in members]
            with toc:
                ui.link(heading, section).classes("sl-toc-head")
                for member, entry in zip(members, entries):
                    ui.link(toc_label(prefix, obj, member), entry).classes("sl-toc-item")

    def api_entry(self, prefix: str, obj, member: str) -> ui.element:
        """One entry of the API reference: signature and docstring (see reference.api_entry())."""
        signature, doc = api_entry(prefix, obj, member)
        with ui.element("div").classes("sl-api-entry sl-anchor") as entry:
            ui.label(signature).classes("sl-signature")
            ui.label(doc).classes("sl-docstring")
        return entry

    # ------------------------------------------------------------------
    def registers(self) -> None:
        """The memory tables of the STS3215 and the XIAO IMU, filterable."""
        columns = [
            {"name": "address", "label": "Addr", "field": "address", "sortable": True, "align": "right"},
            {"name": "name", "label": "Name", "field": "name", "sortable": True, "align": "left",
             "classes": "sl-mono font-semibold"},
            {"name": "size", "label": "Bytes", "field": "size", "align": "right"},
            {"name": "access", "label": "Access", "field": "access", "align": "left", "classes": "whitespace-nowrap"},
            {"name": "memory", "label": "Memory", "field": "memory", "sortable": True, "align": "left"},
            {"name": "unit", "label": "Unit", "field": "unit", "align": "left"},
            {"name": "description", "label": "Description", "field": "description", "align": "left",
             "classes": "whitespace-normal"},
        ]
        tables = [("STS3215 memory table", STS3215_REGISTERS, "m"),
                  ("XIAO IMU memory table", XIAO_IMU_REGISTERS, "imu")]
        toc, content = self.layout()
        for title, registers, variable in tables:
            rows = [{
                "address": r.address, "name": r.name, "size": r.size,
                "access": "read/write" if r.access == "rw" else "read",
                "memory": r.memory.upper(), "unit": r.unit, "description": r.description,
            } for r in registers]
            with content:
                with theme.card().classes("sl-anchor") as section:
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(title).classes("sl-h2")
                        search = ui.input(placeholder="Filter …").props("outlined dense clearable").classes("w-64")
                    ui.label(f"Use these names with {variable}.read_register(name) and "
                             f"{variable}.write_register(name, value). "
                             "Values are raw; the unit column says what one step means.").classes("sl-hint text-[13.5px]")
                    table = ui.table(columns=columns, rows=rows, row_key="name", pagination=0) \
                        .props("flat dense wrap-cells").classes("w-full")
                    search.bind_value_to(table, "filter")
            with toc:
                ui.link(title, section).classes("sl-toc-head")
                ui.label(f"{len(registers)} registers").classes("sl-toc-note")

    # ------------------------------------------------------------------
    def examples(self, examples_dir: Path) -> None:
        """The example scripts, each in a code box."""
        toc, content = self.layout()
        with content:
            ui.label("Copy an example into your own folder and change it. "
                     "Set PORT = \"sim\" to try it without hardware.").classes("sl-hint text-[13.5px]")
        for path in sorted(examples_dir.glob("*.py")):
            with content:
                with theme.card().classes("sl-anchor !gap-2") as section:
                    ui.label(path.name).classes("sl-signature")
                    ui.code(path.read_text(encoding="utf-8"), language="python").classes("w-full text-[13px]")
            with toc:
                ui.link(path.name, section).classes("sl-toc-item")
