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
  mobjects are the most common cause of an unreadable frame.
- Avoid dead air: only hold a frame when the viewer needs a moment on a key result.

## The standard

Purposeful colour, labelled figures, a clean screen, and animation that carries the
explanation rather than accompanying it. Reach for whatever Manim mobject actually fits
the beat - the `on_screen` field is the brief, and there is no house pattern to imitate.
