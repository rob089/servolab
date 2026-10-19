"""
ServoScope doodles: small line-art drawings for empty states, in the style of
the MiMed Robot Learning Hub (ink on paper, exactly one accent element in blue).

Each scene function returns an SVG string; show it with ui.html(...). The parts
(servo, adapter, laptop) are separate functions so new scenes reuse them.

Coordinates: every scene is 280 x 150 units with the ground line at y = 136.
The servo is drawn from the horn side, with the proportions of the STS3215
(45 x 25 mm, output shaft about 10 mm from one end).
"""

from __future__ import annotations

from servolab.scope.theme import ACCENT, INK, PAGE, RAISED, SUNKEN

GROUND = 136
WIDTH, HEIGHT = 280, 150
GREY = "rgba(23, 22, 20, .46)"     # dashed and missing things
FAINT = "rgba(23, 22, 20, .30)"    # inner details
STROKE = 'stroke="{ink}" stroke-width="1.5"'.format(ink=INK)


def svg(title: str, body: str, defs: str = "") -> str:
    """Wrap scene parts into one SVG with the ground line."""
    return (
        f'<svg class="sl-doodle" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{title}">'
        f"<defs>{defs}</defs>{body}"
        f'<line x1="0" y1="{GROUND}" x2="{WIDTH}" y2="{GROUND}" {STROKE}/>'
        "</svg>"
    )


def cable(path: str, dashed: bool = False) -> str:
    """A cable along an SVG path: solid ink, or dashed grey for "not plugged in"."""
    if dashed:
        return f'<path d="{path}" fill="none" stroke="{GREY}" stroke-width="1.6" stroke-dasharray="4 3" stroke-linecap="round"/>'
    return f'<path d="{path}" fill="none" stroke="{INK}" stroke-width="2.2" stroke-linecap="round"/>'


# ---------------------------------------------------------------------------
# Parts
# ---------------------------------------------------------------------------

def servo(x: float, missing: bool = False) -> str:
    """An STS3215 standing on the ground, horn up. x = left edge (34 wide, 60 high)."""
    top = GROUND - 60
    cx, cy = x + 17, top + 14            # the horn sits near the top end, not in the middle
    if missing:   # a dashed outline on hatching: "a motor should be here"
        return (
            f'<rect x="{x}" y="{top}" width="34" height="60" rx="4" fill="url(#sl-hatch)" '
            f'stroke="{GREY}" stroke-width="1.5" stroke-dasharray="4 3"/>'
            f'<circle cx="{cx}" cy="{cy}" r="13" fill="none" stroke="{GREY}" stroke-width="1.3" stroke-dasharray="3 3"/>'
        )
    return (
        f'<rect x="{x}" y="{top}" width="34" height="60" rx="4" fill="{RAISED}" {STROKE}/>'
        f'<circle cx="{cx}" cy="{cy}" r="13" fill="{RAISED}" {STROKE}/>'
        f'<circle cx="{cx}" cy="{cy}" r="8.5" fill="none" stroke="{FAINT}" stroke-width="1.1"/>'
        f'<circle cx="{cx}" cy="{cy}" r="3.4" fill="{PAGE}" {STROKE}/>'
        f'<path d="M{x + 8} {GROUND - 12} H{x + 26} M{x + 8} {GROUND - 7.5} H{x + 26}" '
        f'fill="none" stroke="{GREY}" stroke-width="1.2" stroke-linecap="round"/>'
    )


def adapter(x: float, lit: bool = False) -> str:
    """The Waveshare bus adapter: USB socket left, status LED right. x = left edge."""
    led = ACCENT if lit else "none"
    return (
        f'<rect x="{x}" y="100" width="38" height="24" rx="3" fill="{RAISED}" {STROKE}/>'
        f'<rect x="{x}" y="107" width="5" height="9" fill="{INK}"/>'
        f'<circle cx="{x + 30}" cy="107" r="2.5" fill="{led}" stroke="{INK}" stroke-width="1.2"/>'
    )


def laptop(x: float) -> str:
    """A laptop standing on the ground. x = left edge of the base."""
    return (
        f'<path d="M{x} {GROUND} L{x + 10} 124 L{x + 66} 124 L{x + 76} {GROUND}Z" fill="{RAISED}" {STROKE} '
        'stroke-linejoin="round"/>'
        f'<rect x="{x + 12}" y="80" width="52" height="44" rx="4" fill="{RAISED}" {STROKE}/>'
        f'<rect x="{x + 18}" y="86" width="40" height="32" rx="2" fill="{SUNKEN}" stroke="{INK}" stroke-width="1.2"/>'
    )


def usb_plug(x: float, y: float, accent: bool = False) -> str:
    """The plug of a USB cable: a 12 x 12 square, left edge x, centred on height y.

    accent=True fills it with the accent colour.
    """
    fill = ACCENT if accent else RAISED
    return f'<rect x="{x}" y="{y - 6}" width="12" height="12" rx="2" fill="{fill}" {STROKE}/>'


HATCH = (
    '<pattern id="sl-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
    f'<rect width="7" height="7" fill="{PAGE}"/><rect width="3.5" height="7" fill="{SUNKEN}"/></pattern>'
)


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------

def not_connected() -> str:
    """Laptop, USB plug pulled out (blue), adapter, motor."""
    body = (
        laptop(14)
        + cable("M86 130 C106 130 106 111 124 111")
        + usb_plug(124, 111, accent=True)
        + f'<path d="M140 111 L154 111" fill="none" stroke="{GREY}" stroke-width="1.3" '
          'stroke-dasharray="3 4" stroke-linecap="round"/>'
        + adapter(156)
        + cable("M194 118 C210 118 212 128 224 128")
        + servo(224)
    )
    return svg("Drawing: the USB cable of the adapter is not plugged in", body)


def no_motors() -> str:
    """Adapter plugged in and on (blue light), but the cable leads to empty slots."""
    body = (
        cable("M0 111 L12 111")
        + usb_plug(12, 111)
        + adapter(24, lit=True)
        + cable("M62 118 C74 118 76 128 86 128")
        + cable("M120 128 L150 128 M184 128 L214 128", dashed=True)
        + servo(86, missing=True) + servo(150, missing=True) + servo(214, missing=True)
    )
    return svg("Drawing: the adapter is connected, but no device on the bus answers", body, defs=HATCH)
