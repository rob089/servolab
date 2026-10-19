"""
Generates the pages of the documentation website that come from the package
itself, so they never go out of date (run by the mkdocs-gen-files plugin):

- guides/*.md     copies of src/servolab/docs/*.md (the same guides ServoScope shows)
- api.md          signatures and docstrings, the same entries as in ServoScope
- registers.md    the memory tables from src/servolab/registers.py
- examples.md     the scripts in examples/
- changelog.md    CHANGELOG.md
- assets/         the ServoScope icon, used as logo and favicon
"""

import html
import inspect
from pathlib import Path

import mkdocs_gen_files

import servolab
from servolab.registers import STS3215_REGISTERS, XIAO_IMU_REGISTERS
from servolab.scope.reference import API, DOCS_DIR, GUIDES, api_entry, first_paragraph, toc_label

ROOT = Path(__file__).resolve().parent.parent


def write(path, text):
    """Write one generated page (it only exists while mkdocs builds the site)."""
    with mkdocs_gen_files.open(path, "w") as file:
        file.write(text)


def anchor(heading, member):
    """A unique, readable id for an API entry, e.g. "bus-move_to"."""
    return f"{heading.lower()}-{member.strip('_')}"


# --- Guides -------------------------------------------------------------------
for filename, _ in GUIDES:
    write(f"guides/{filename}", (DOCS_DIR / filename).read_text(encoding="utf-8"))

# --- Python API ---------------------------------------------------------------
lines = [
    "# Python API",
    "",
    f"servolab {servolab.__version__}. Everything here is also in Python itself: "
    "`help(servolab.connect)`, `help(m.move_to)` ... and on the documentation page of ServoScope. "
    "All values are in SI units (rad, rad/s, A, V, °C), see [Modes & units](guides/modes_and_units.md).",
    "",
]
for heading, prefix, obj, members in API:
    lines += [f"## {heading}", ""]
    if inspect.isclass(obj) and inspect.getdoc(obj):
        lines += [first_paragraph(inspect.getdoc(obj)), ""]
    for member in members:
        signature, doc = api_entry(prefix, obj, member)
        lines += [
            f"### `{toc_label(prefix, obj, member)}` {{ #{anchor(heading, member)} }}",
            "",
            "```python",
            signature,
            "```",
            "",
            # The docstrings are written as plain text (for help() and ServoScope):
            # keep their line breaks and indentation instead of reading them as Markdown.
            f'<div class="sl-docstring">{html.escape(doc)}</div>',
            "",
        ]
write("api.md", "\n".join(lines))

# --- Registers ----------------------------------------------------------------
lines = [
    "---",
    "hide:",
    "  - toc",            # the tables need the width
    "---",
    "",
    "# Registers",
    "",
    "The memory table inside each device. Use the names with `m.read_register(name)` and "
    "`m.write_register(name, value)` (or `imu.` for the IMU). Values are raw integers; the unit "
    "column says what one step means. EEPROM values are kept after power-off only when written "
    "with `save=True` (see [Modes & units](guides/modes_and_units.md)).",
    "",
]
for title, registers in (("STS3215 (and STS3250)", STS3215_REGISTERS), ("XIAO IMU", XIAO_IMU_REGISTERS)):
    lines += [
        f"## {title}",
        "",
        "| Addr | Name | Bytes | Access | Unit | Description |",
        "|-----:|------|------:|--------|------|-------------|",
    ]
    for r in registers:
        access = f"{'read/write' if r.access == 'rw' else 'read'}, {r.memory.upper()}"
        description = r.description.replace("|", "\\|")
        lines.append(f"| {r.address} | `{r.name}` | {r.size} | {access} | {r.unit} | {description} |")
    lines.append("")
write("registers.md", "\n".join(lines))

# --- Examples -----------------------------------------------------------------
lines = [
    "# Examples",
    "",
    "Small programs to start from, in the `examples/` folder of the repository. They go step by "
    "step from connecting to plotting. Set `PORT = \"sim\"` to try them without hardware.",
    "",
]
for path in sorted((ROOT / "examples").glob("*.py")):
    lines += [f"## {path.name}", "", "```python", path.read_text(encoding="utf-8").rstrip(), "```", ""]
write("examples.md", "\n".join(lines))

# --- Changelog and assets -----------------------------------------------------
write("changelog.md", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
with mkdocs_gen_files.open("assets/favicon.png", "wb") as file:
    file.write((ROOT / "src/servolab/scope/assets/favicon.png").read_bytes())
