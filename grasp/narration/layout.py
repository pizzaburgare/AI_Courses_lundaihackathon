"""Deterministic layout checks, run at every ``self.play`` boundary inside the render.

Geometry, not vision: the whole check is bounding boxes against the frame and against
each other. It costs nothing, it is the same answer every run, and it names the offending
object by the string it renders so the next attempt can find it in the file.
"""

from manim import Scene, config
from manim.mobject.mobject import Mobject
from manim.mobject.text.numbers import DecimalNumber
from manim.mobject.text.tex_mobject import SingleStringMathTex
from manim.mobject.text.text_mobject import MarkupText, Text

from grasp.core import Violation

# MathTex, Tex, Title and BulletedList all subclass SingleStringMathTex; Integer
# subclasses DecimalNumber. Their submobjects are MathTexPart / VMobjectFromSVGPath,
# so a family walk never yields a nested match and nothing overlaps itself.
TEXTUAL = (Text, MarkupText, SingleStringMathTex, DecimalNumber)

EDGE_MARGIN = 0.05  # scene units a box may poke past the frame before it counts
MIN_OVERLAP_FRACTION = 0.15  # ignore intersections below this share of the smaller box
MIN_OPACITY = 0.01

Box = tuple[float, float, float, float]  # (left, right, bottom, top)


def label(mobject: Mobject) -> str:
    """Best-effort identity: the class plus the string it renders.

    ``original_text`` first. ``Text.text`` has had its spaces and newlines stripped
    (``manim/mobject/text/text_mobject.py:530``), so a violation on ``Text("way out
    there")`` would be reported as ``Text('wayoutthere')`` - unfindable by a model
    rewriting the file, which is the whole point of naming it.
    """
    for attribute in ("original_text", "text", "tex_string"):
        value = getattr(mobject, attribute, None)
        if value:
            return f"{type(mobject).__name__}({str(value)[:40]!r})"
    return type(mobject).__name__


def on_screen_text(scene: Scene) -> list[Mobject]:
    """Every visible Text / Tex / DecimalNumber currently in *scene*, deduplicated.

    Visible means it has points and some part of it has non-zero fill or stroke opacity,
    so a mobject that has been faded out is not reported as overlapping its replacement.
    """
    found: dict[int, Mobject] = {}
    for top in scene.mobjects:
        for mobject in top.get_family():
            if not isinstance(mobject, TEXTUAL):
                continue
            for part in mobject.family_members_with_points():
                opacity = max(float(part.get_fill_opacity()), float(part.get_stroke_opacity()))
                if opacity > MIN_OPACITY:
                    found[id(mobject)] = mobject
                    break
    return list(found.values())


def check_layout(scene: Scene) -> list[Violation]:
    """Every on-screen text box that leaves the frame, and every pair that intersects."""
    now = float(scene.renderer.time)
    boxes: list[tuple[Mobject, Box]] = [
        (
            mobject,
            (
                float(mobject.get_left()[0]),
                float(mobject.get_right()[0]),
                float(mobject.get_bottom()[1]),
                float(mobject.get_top()[1]),
            ),
        )
        for mobject in on_screen_text(scene)
    ]
    violations: list[Violation] = []

    x_radius, y_radius = config.frame_x_radius, config.frame_y_radius
    for mobject, (left, right, bottom, top) in boxes:
        past = max(-x_radius - left, right - x_radius, -y_radius - bottom, top - y_radius)
        if past > EDGE_MARGIN:
            violations.append(
                Violation(at=now, problem=f"{label(mobject)} is {past:.2f} units past the frame")
            )

    for index, (first, a) in enumerate(boxes):
        for second, b in boxes[index + 1 :]:
            width = min(a[1], b[1]) - max(a[0], b[0])
            height = min(a[3], b[3]) - max(a[2], b[2])
            if width <= 0 or height <= 0:
                continue
            smallest = min((a[1] - a[0]) * (a[3] - a[2]), (b[1] - b[0]) * (b[3] - b[2]))
            share = (width * height) / smallest if smallest > 0 else 1.0
            if share > MIN_OVERLAP_FRACTION:
                violations.append(
                    Violation(
                        at=now,
                        problem=(
                            f"{label(first)} overlaps {label(second)} over "
                            f"{share:.0%} of the smaller box"
                        ),
                    )
                )
    return violations
