"""Step 3, second half: one video's brief -> that video's script.

``topics.json`` already named this topic's sources and :mod:`grasp.script.outline` already
decided which video teaches what, so nothing here chooses documents or divides material.
This asks for one beat list against one part's brief.

The brief is what keeps a series honest. Part *n* is told the points assigned to it and
the points assigned to every other part, so it can neither re-teach part 1 nor quietly
drop material because it ran out of things to say.

Data in, data out. This is also the only place video length is decided: the word count in
the brief is the running time, at :data:`grasp.core.WORDS_PER_MINUTE`. It is asked for, not
enforced - what a beat is worth in words is an editorial judgement, and those belong in
``prompt.md`` where they can be argued with, not in a rejection the model cannot answer.
"""

from math import ceil
from pathlib import Path

from grasp.core import (
    LANGUAGE_RULE,
    MINUTES_PER_VIDEO,
    WORDS_PER_MINUTE,
    Outline,
    Script,
    Topic,
    ask_valid,
)
from grasp.script.sources import neighbour_block, source_block

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
INSTRUCTIONS = PROMPT + "\n" + LANGUAGE_RULE


def part_count(minutes: int) -> int:
    """The most videos a topic of *minutes* may become. The outline may use fewer."""
    return max(1, ceil(minutes / MINUTES_PER_VIDEO))


def target_words(minutes: int, parts: int) -> int:
    """Narration words one part should come to, given the topic's estimate.

    Capped at :data:`grasp.core.MINUTES_PER_VIDEO`, so a topic the outline collapses into
    fewer parts than its estimate allowed does not become one overlong video.
    """
    return round(min(minutes / parts, MINUTES_PER_VIDEO) * WORDS_PER_MINUTE)


def write_script(
    topic: Topic,
    sources: dict[str, str],
    outline: Outline,
    part: int,
    neighbours: list[Topic] | None = None,
) -> Script:
    """The beat list for video *part* of *topic*, against its brief in *outline*.

    *sources* maps each corpus-relative path in ``topic.sources`` to that document's
    markdown. *outline* holds one brief per video of this topic; a topic that is one video
    may pass an outline whose single part lists no points, and this video then covers the
    whole concept. *neighbours* is every other topic of the course - a one-video topic never
    goes through the outline stage, so this is the only thing telling it that the topic
    before it exists.
    """
    missing = [path for path in topic.sources if path not in sources]
    if missing:
        raise ValueError(f"topic {topic.id} is missing source text for {', '.join(missing)}")

    briefs = {entry.part: entry for entry in outline.parts}
    if part not in briefs:
        known = ", ".join(str(number) for number in sorted(briefs)) or "none"
        raise ValueError(f"topic {topic.id} has no part {part} in its outline (have: {known})")

    parts = len(outline.parts)
    mine = briefs[part]
    target = target_words(topic.minutes, parts)

    lines = [
        f"# Topic {topic.id} - {topic.title}",
        "",
        topic.summary.strip(),
        "",
        f"This is video {part} of {parts} for this topic, titled {mine.title!r}.",
        f"Aim for about {target} narration words; that is what sets the running time.",
    ]

    if mine.covers:
        lines += ["", "## What this video teaches", ""]
        lines += [f"- {point}" for point in mine.covers]
        lines += ["", "Teach all of these points, and no material outside them."]
    else:
        lines += ["", "This is the only video for this concept; cover the whole of it."]

    others = [entry for entry in outline.parts if entry.part != part]
    if others:
        lines += ["", "## What the other videos of this topic teach", ""]
        for entry in others:
            lines += [f"Video {entry.part} - {entry.title}:"]
            lines += [f"  - {point}" for point in entry.covers]
        lines += [
            "",
            "None of that belongs to you. Do not teach it, do not re-derive it and do not",
            "recap it: a one-sentence callback to an earlier video is welcome, a recap",
            "section is not. Trust that the other videos do their own job.",
        ]

    lines += neighbour_block(topic, neighbours or [])
    lines += source_block(topic.sources, sources)

    def check(result: Script) -> list[str]:
        """The two ways a beat is unusable to the next step. Length is the prompt's job."""
        problems: list[str] = []
        for number, beat in enumerate(result.beats, start=1):
            if not beat.narration.strip():
                problems.append(f"beat {number} ({beat.title!r}) narrates nothing")
            if not beat.on_screen.strip():
                problems.append(f"beat {number} ({beat.title!r}) says nothing about the screen")
        return problems

    result = ask_valid(INSTRUCTIONS, "\n".join(lines), Script, check)
    return result.model_copy(update={"topic_id": topic.id, "part": part, "parts": parts})
