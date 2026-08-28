"""A broken ``scene.py``, debugged by an agent instead of re-sampled from scratch.

:mod:`grasp.pipeline` answers a failed render by calling :func:`grasp.scene.build_scene`
again with a tail of the failure text. That throws the file away: the model never sees the
line the traceback names, and every beat that already rendered is rewritten on the chance
that the crash was somewhere in it.

This is the other shape. One pydantic-ai agent gets three tools - read the file, write the
file, run the render - and works the way a person does: look at the traceback, look at the
line it names, change that line, render again. Nothing here knows what a course is; the
caller passes the file and a way to render it, which is what lets the trial at the bottom
of this module test it against a scene broken on purpose instead of a whole pipeline run.

    uv run python -m grasp.scene.fix [--model MODEL] [--renders N]
"""

import argparse
import ast
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from grasp.core import CODE_MODEL, ROOT

load_dotenv()

MAX_RENDERS = 4  # renders, not model calls: the render is what costs minutes
REPORT_TAIL_CHARS = 4_000  # of a failure report, the end is the part that says why

INSTRUCTIONS = """You fix a Manim scene that does not render.

Work like a debugger, not like an author. The file is mostly right - one or a few lines
are wrong. Read it, find what the traceback actually names, change the smallest thing that
can be the cause, and render again. Never rewrite the file from scratch and never delete
content to make an error go away: every animation and every line of narration that is
there now must still be there when you are done.

Renders are expensive and you have very few. Before spending one, fix everything you can
already see: a traceback names the first crash, not the only one.

Stop as soon as `render` reports RENDER OK. Your final answer is two or three sentences on
what was wrong and what you changed - no code."""


@dataclass
class Bench:
    """The one file the agent is working on, and what it is allowed to spend on it."""

    scene: Path
    render: Callable[[], tuple[bool, str]]
    max_renders: int = MAX_RENDERS
    renders: int = 0
    passed: bool = False


AGENT: Agent[Bench, str] = Agent(deps_type=Bench, output_type=str, instructions=INSTRUCTIONS)


@AGENT.tool
def read_scene(ctx: RunContext[Bench]) -> str:
    """Read the current scene file. Returns its source with line numbers."""
    lines = ctx.deps.scene.read_text(encoding="utf-8").splitlines()
    return "\n".join(f"{number:4d} | {line}" for number, line in enumerate(lines, start=1))


@AGENT.tool
def write_scene(ctx: RunContext[Bench], source: str) -> str:
    """Replace the scene file with *source*, the complete contents of the file."""
    try:
        ast.parse(source)
    except SyntaxError as err:
        return f"not written - that source does not parse: {err}"
    ctx.deps.scene.write_text(source.rstrip() + "\n", encoding="utf-8")
    return f"written, {len(source.splitlines())} lines. Render it to find out whether it works."


@AGENT.tool
def render(ctx: RunContext[Bench]) -> str:
    """Render the scene file as it stands now. Returns RENDER OK, or the failure."""
    bench = ctx.deps
    if bench.renders >= bench.max_renders:
        return f"no renders left - all {bench.max_renders} are spent. Answer with what is wrong."
    bench.renders += 1
    ok, report = bench.render()
    bench.passed = ok
    if ok:
        return "RENDER OK - the scene rendered. Stop here and report what you changed."
    return (
        f"render {bench.renders} of {bench.max_renders} failed:\n\n"
        + report.strip()[-REPORT_TAIL_CHARS:]
    )


def fix_scene(
    scene: Path,
    render_scene: Callable[[], tuple[bool, str]],
    failure: str = "",
    rules: str = "",
    model: str = CODE_MODEL,
    max_renders: int = MAX_RENDERS,
) -> tuple[bool, str, int]:
    """Debug *scene* in place until it renders. Returns (rendered, what it says it did, renders).

    *render_scene* renders the file as it stands and returns whether it worked and the
    failure text if it did not. *failure* is the report from the render that got us here,
    so the agent starts on the traceback instead of spending a render finding it. *rules*
    is the contract the file has to keep - for the pipeline that is ``api.md``.

    The verdict is the render's, never the model's: the flag comes back from the last
    render the agent actually ran.
    """
    bench = Bench(scene=scene, render=render_scene, max_renders=max_renders)
    client = OpenAIChatModel(
        model, provider=OpenRouterProvider(api_key=os.getenv("OPENROUTER_API_KEY") or "")
    )
    prompt = [f"The scene that will not render is {scene}."]
    if rules:
        prompt += ["", "# What this file has to be", "", rules.strip()]
    if failure:
        prompt += ["", "# How it failed", "", failure.strip()[-REPORT_TAIL_CHARS:]]
    prompt += ["", "Read it, fix it, and render it."]

    result = AGENT.run_sync("\n".join(prompt), deps=bench, model=client)
    return bench.passed, result.output.strip(), bench.renders


# --- the trial: one scene broken on purpose, no course, no corpus, no TTS ------------------

WORK = ROOT / ".cache" / "fix-trial"
RENDER_TIMEOUT_SECONDS = 600
STDERR_TAIL_LINES = 40

RULES = (
    "A standalone Manim Community Edition 0.20 scene: one class `Lesson(Scene)` with one "
    "`construct`, rendered as `manim -ql scene.py Lesson`. `from manim import *` and numpy "
    "are the only imports it needs. There is no narration in this file."
)

# The bugs a code model actually produces: a name Manim CE renamed, a British spelling, and
# a two-element point. Only the first is in the first traceback, so a run that passes is a
# run where the agent went back and read the file.
BROKEN = """from manim import *
import numpy as np


class Lesson(Scene):
    def construct(self):
        title = Text("Little's Law", font_size=48).to_edge(UP)
        self.play(ShowCreation(title))

        box = Square(side_length=2)
        box.set_colour(BLUE)
        self.play(FadeIn(box))

        label = Text("L = lambda W", font_size=32)
        label.move_to(np.array([0, -2.5]))
        self.play(Write(label))
        self.wait(0.5)
"""


def render_once(scene: Path) -> tuple[bool, str]:
    """Render *scene* at draft quality. Returns (it worked, the tail of the failure)."""
    command = [
        sys.executable,
        "-m",
        "manim",
        "-ql",
        "--media_dir",
        str(scene.parent / "manim"),
        str(scene),
        "Lesson",
    ]
    print(f"  rendering {scene.name} ...", flush=True)
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=RENDER_TIMEOUT_SECONDS, check=False
    )
    if result.returncode == 0:
        print("  render ok", flush=True)
        return True, ""
    tail = "\n".join(f"{result.stdout}\n{result.stderr}".strip().splitlines()[-STDERR_TAIL_LINES:])
    print(f"  render failed ({result.returncode})", flush=True)
    return False, f"manim exited {result.returncode}\n\n{tail}"


def main() -> None:
    """Break a scene, run the agent on it, and say whether the render came back."""
    parser = argparse.ArgumentParser(description="Try the fix agent on a scene broken on purpose.")
    parser.add_argument("--model", default=CODE_MODEL, help="OpenRouter model for the agent")
    parser.add_argument("--renders", type=int, default=MAX_RENDERS, help="renders it may spend")
    args = parser.parse_args()

    WORK.mkdir(parents=True, exist_ok=True)
    scene = WORK / "scene.py"
    scene.write_text(BROKEN, encoding="utf-8")
    print(f"broken scene written to {scene}\n\nthe render the pipeline would have failed on:")

    ok, failure = render_once(scene)
    if ok:
        print("\nthe broken scene rendered - this trial proves nothing")
        raise SystemExit(1)
    print(f"\n{failure}\n\nhanding it to the agent on {args.model}\n")

    fixed, said, renders = fix_scene(
        scene,
        lambda: render_once(scene),
        failure=failure,
        rules=RULES,
        model=args.model,
        max_renders=args.renders,
    )
    print(f"\n--- {scene} after the agent ---\n{scene.read_text(encoding='utf-8')}")
    print(f"--- the agent says ---\n{said}\n")
    print(f"verdict: {'FIXED' if fixed else 'still broken'} after {renders} render(s)")
    raise SystemExit(0 if fixed else 1)


if __name__ == "__main__":
    main()
