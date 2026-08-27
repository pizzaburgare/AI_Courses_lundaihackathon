# How the video should teach and look

Take great inspiration from 3blue1brown: the visual carries the argument, and the voice
explains why the visual is doing what it does. The script has already decided what is said
and what is on screen. Your job is to realise that faithfully and beautifully.

## Visual language

- **Colour encodes meaning, never decoration.** Fix one legend per scene and reuse it,
  for example `BLUE` = the baseline object, `GREEN` = the result, `YELLOW` = the active
  marker, `RED` = the error or the thing being rejected.
- **Text stays white by default.** Colour a label only when it maps to a coloured element
  in the diagram. Never pick a text colour for style.
- Prefer a figure to a sentence. Use `Axes` and `NumberPlane` for anything with
  coordinates, `MathTex` for every equation, arrows and braces to point at the part of a
  formula being discussed (`SurroundingRectangle`, `Brace`, `Indicate`).
- Keep the problem statement or governing equation parked at the top or in a corner while
  it is being worked on, so the viewer never loses the context.
- Motion should mean something: `ValueTracker` plus `always_redraw` or `add_updater` for
  anything that varies, `ReplacementTransform` to show one expression *becoming* another
  rather than being replaced by it.
- Label numbers and axes. An unlabelled axis teaches nothing.
- Reveal in the order the narration builds the idea - `Write` the term being named as it
  is named, not the whole formula at once.
- Remove what the next beat does not need. A tidy screen is a readable screen, and stale
  mobjects are the most common cause of a failed layout check.
- Avoid dead air: only hold a frame when the viewer needs a moment on a key result.

## Worked examples

These show the shape of a good file: one `Lesson(Scene)`, one `Narrator`, one `say()`
block per beat, chapter markers at real chapter boundaries, `finish()` last.

### A graph, and a dot descending to its lowest point

```python
from pathlib import Path

from manim import *

from grasp.narration import Narrator
import numpy as np


class Lesson(Scene):
    def construct(self):
        narrator = Narrator(self, Path(__file__).parent)

        # ==========================================================
        # Introduction
        # ==========================================================
        narrator.new_section("Introduction")
        title = Title("Understanding the Argmin")
        func_text = MathTex("f(x) = 2(x - 5)^2").scale(0.8).to_corner(UP + RIGHT)

        with narrator.say("Welcome. Today, let us illuminate a beautiful distinction in mathematics: the difference between a minimum value, and the arg min."):
            self.play(Write(title))

        # ==========================================================
        # Setting up the graph
        # ==========================================================
        ax = Axes(x_range=[0, 10], y_range=[0, 100, 10], axis_config={"include_tip": False})
        labels = ax.get_axis_labels(x_label="x", y_label="f(x)")

        def func(x):
            return 2 * (x - 5) ** 2

        graph = ax.plot(func, color=BLUE)

        with narrator.say("Consider this parabola. It represents a cost curve that we wish to minimise."):
            self.play(Create(ax), Write(labels))
            self.play(Create(graph), Write(func_text))

        # ==========================================================
        # The minimum versus the argmin
        # ==========================================================
        narrator.new_section("Minimum versus argmin")
        t = ValueTracker(0)
        dot = Dot(point=ax.c2p(0, func(0)), color=YELLOW).scale(1.2)
        dot.add_updater(lambda m: m.move_to(ax.c2p(t.get_value(), func(t.get_value()))))

        with narrator.say("If we begin our search at x equals zero, the function's value is high. We naturally want to descend to the lowest point."):
            self.play(FadeIn(dot))

        x_space = np.linspace(*ax.x_range[:2], 200)
        target_x = x_space[func(x_space).argmin()]

        with narrator.say("The minimum is the lowest value on the vertical axis. But the arg min asks a deeper question: which input x produces that lowest value?"):
            self.play(Indicate(func_text))

        with narrator.say("Let us slide along the curve, seeking the horizontal position that minimises our height."):
            self.play(t.animate.set_value(target_x), run_time=3)

        # ==========================================================
        # Conclusion
        # ==========================================================
        narrator.new_section("Conclusion")
        dot.clear_updaters()
        line = DashedLine(start=ax.c2p(target_x, func(target_x) + 20), end=ax.c2p(target_x, 0))
        argmin_text = MathTex(r"\arg\min_{x} f(x) = 5").scale(0.8).next_to(line, UP, buff=0.2)

        with narrator.say("And here we arrive. The minimum value of the function is zero, but the arg min is exactly five. We have found the source of the optimal outcome."):
            self.play(Create(line), Write(argmin_text))

        narrator.finish()
```

Every narration argument is one unbroken string literal on one line, however long the
line gets. That is deliberate: the audio is pre-synthesised by reading these literals.

### Building the sine wave out of the unit circle

```python
from pathlib import Path

from manim import *

from grasp.narration import Narrator
import numpy as np


class Lesson(Scene):
    def construct(self):
        narrator = Narrator(self, Path(__file__).parent)

        narrator.new_section("Setup")
        origin_point = np.array([-4, 0, 0])
        curve_start = np.array([-3, 0, 0])

        x_axis = Line(np.array([-6, 0, 0]), np.array([6, 0, 0]))
        y_axis = Line(np.array([-4, -2, 0]), np.array([-4, 2, 0]))

        x_labels = VGroup()
        for i, text in enumerate([r"\pi", r"2 \pi", r"3 \pi", r"4 \pi"]):
            x_labels.add(MathTex(text).scale(0.8).next_to(np.array([-1 + 2 * i, 0, 0]), DOWN))

        with narrator.say("On the left we place the unit circle; on the right, a timeline."):
            self.play(Create(x_axis), Create(y_axis), FadeIn(x_labels))

        circle = Circle(radius=1, color=BLUE).move_to(origin_point)
        title = Title("Generating the Sine Wave").scale(0.8)

        with narrator.say("The circle is a cycle that repeats forever. How do we unroll it?"):
            self.play(Create(circle), Write(title))

        narrator.new_section("The moving parts")
        dot = Dot(radius=0.1, color=YELLOW).move_to(circle.point_from_proportion(0))
        radius_line = always_redraw(lambda: Line(origin_point, dot.get_center(), stroke_width=2))
        t_tracker = ValueTracker(0)

        projection = always_redraw(
            lambda: Line(
                dot.get_center(),
                np.array([curve_start[0] + t_tracker.get_value() * 4, dot.get_center()[1], 0]),
                stroke_width=2,
            )
        )
        trace = TracedPath(
            lambda: np.array(
                [curve_start[0] + t_tracker.get_value() * 4, dot.get_center()[1], 0]
            ),
            stroke_width=3,
            stroke_color=GREEN,
        )

        with narrator.say("We track one point orbiting the centre, and watch only its height."):
            self.play(FadeIn(dot), Create(radius_line))

        self.add(projection, trace)
        dot.add_updater(lambda m: m.move_to(circle.point_from_proportion(t_tracker.get_value() % 1)))

        with narrator.say("As we rotate, that height is projected sideways, and a wave appears."):
            self.play(t_tracker.animate.set_value(2.0), run_time=8, rate_func=linear)

        narrator.new_section("Conclusion")
        dot.clear_updaters()
        final_text = Text("Periodic Motion", font_size=36).next_to(trace, UP)

        with narrator.say("The sine wave is a history of the circle's vertical position."):
            self.play(Write(final_text))

        narrator.finish()
```

### Framing the terms of an equation

```python
from pathlib import Path

from manim import *

from grasp.narration import Narrator


class Lesson(Scene):
    def construct(self):
        narrator = Narrator(self, Path(__file__).parent)

        narrator.new_section("The product rule")
        title = Title("The Product Rule")
        equation = MathTex(
            r"\frac{d}{dx}(f(x)g(x)) =",
            r"f(x)\frac{d}{dx}g(x)",
            r"+",
            r"g(x)\frac{d}{dx}f(x)",
        ).scale(1.1)

        with narrator.say("Let us visualise the rhythm of the product rule."):
            self.play(Write(title))
            self.play(Write(equation))

        box1 = SurroundingRectangle(equation[1], buff=0.1, color=BLUE)
        with narrator.say("First we hold the first function fixed, and multiply by the derivative of the second."):
            self.play(Create(box1))

        box2 = SurroundingRectangle(equation[3], buff=0.1, color=GREEN)
        with narrator.say("Then the symmetric counterpart: the second held fixed, times the derivative of the first."):
            self.play(ReplacementTransform(box1, box2))

        with narrator.say("Left d-right, plus right d-left. A balancing act of rates of change."):
            self.play(FadeOut(box2), Wiggle(equation[2]))

        narrator.finish()
```

Match the quality of these: purposeful colour, labelled figures, a clean screen, and
animation that carries the explanation rather than accompanying it.
