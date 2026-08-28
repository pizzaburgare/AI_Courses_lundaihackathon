"""Step 3, second half: one video's brief -> that video's script.

``topics.json`` already named this topic's sources and :mod:`grasp.script.outline` already
decided which video teaches what, so nothing here chooses documents or divides material.
This asks for one beat list against one part's brief.

The brief is what keeps a series honest. Part *n* is told the points assigned to it and
the points assigned to every other part, so it can neither re-teach part 1 nor quietly
drop material because it ran out of things to say.

Data in, data out. This is also the only place video length is controlled - the word count
is the running time, at :data:`grasp.core.WORDS_PER_MINUTE`.
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

MAX_BEAT_WORDS = 60  # a longer beat is a static screen with a voice over it
MIN_BEAT_WORDS = 12  # a shorter one is a caption, and breaks the rhythm
MIN_BEATS = 4
WORD_TOLERANCE = 0.30  # how far off the target word count a script may land


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
    low, high = round(target * (1 - WORD_TOLERANCE)), round(target * (1 + WORD_TOLERANCE))

    lines = [
        f"# Topic {topic.id} - {topic.title}",
        "",
        topic.summary.strip(),
        "",
        f"This is video {part} of {parts} for this topic, titled {mine.title!r}.",
        f"Aim for about {target} narration words, and stay between {low} and {high}.",
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
        problems: list[str] = []
        if len(result.beats) < MIN_BEATS:
            problems.append(f"only {len(result.beats)} beats; a video needs at least {MIN_BEATS}")
        for number, beat in enumerate(result.beats, start=1):
            if not beat.on_screen.strip():
                problems.append(f"beat {number} ({beat.title!r}) says nothing about the screen")
            words = len(beat.narration.split())
            if not words:
                problems.append(f"beat {number} ({beat.title!r}) narrates nothing")
            elif words > MAX_BEAT_WORDS:
                problems.append(
                    f"beat {number} ({beat.title!r}) narrates {words} words, over the "
                    f"{MAX_BEAT_WORDS}-word ceiling. Split it into two beats."
                )
            elif words < MIN_BEAT_WORDS:
                problems.append(
                    f"beat {number} ({beat.title!r}) narrates only {words} words. Say "
                    f"something worth a beat, or fold it into its neighbour."
                )
        total = result.words()
        if total > high:
            problems.append(
                f"the narration is {total} words across {len(result.beats)} beats, "
                f"{total - high} words over the {high}-word maximum. Cut about "
                f"{total - high} words: tighten the wordiest beats, or drop one."
            )
        elif total < low:
            problems.append(
                f"the narration is {total} words across {len(result.beats)} beats, "
                f"{low - total} words under the {low}-word minimum. Add about "
                f"{low - total} words: go deeper on a point you asserted, or add a beat."
            )
        return problems

    result = ask_valid(INSTRUCTIONS, "\n".join(lines), Script, check)
    return result.model_copy(update={"topic_id": topic.id, "part": part, "parts": parts})
