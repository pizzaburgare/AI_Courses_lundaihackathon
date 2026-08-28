"""Step 3: one topic -> one or more video scripts.

``topics.json`` already named this topic's sources, so no model chooses documents here:
the caller reads them, this module excerpts them and asks for one beat list per video.

A topic estimated at more than :data:`grasp.core.MINUTES_PER_VIDEO` minutes becomes
several videos. Part *n* is written with parts 1..*n*-1 in front of it, which is why the
parts are asked for one at a time rather than in a single call: part 2 has to be able to
say "we showed this last time" and mean it.

Data in, data out. This is also the only place video length is controlled - the word
count is the running time, at :data:`grasp.core.WORDS_PER_MINUTE`.
"""

from math import ceil
from pathlib import Path

from grasp.core import (
    LANGUAGE_RULE,
    MINUTES_PER_VIDEO,
    WORDS_PER_MINUTE,
    Script,
    Topic,
    ask_valid,
)

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
INSTRUCTIONS = PROMPT + "\n" + LANGUAGE_RULE

SOURCE_BUDGET_CHARS = 150_000  # total across all of a topic's sources
MAX_BEAT_WORDS = 60  # a longer beat is a static screen with a voice over it
MIN_BEATS = 4
WORD_TOLERANCE = 0.25  # how far off the target word count a script may land

TRUNCATED = "\n\n[... source truncated to fit the context budget ...]"


def part_count(minutes: int) -> int:
    """How many videos a topic of *minutes* becomes."""
    return max(1, ceil(minutes / MINUTES_PER_VIDEO))


def target_words(minutes: int, parts: int) -> int:
    """Narration words one part should come to, given the topic's estimate."""
    return round(minutes / parts * WORDS_PER_MINUTE)


def write_script(
    topic: Topic,
    sources: dict[str, str],
    part: int = 1,
    parts: int = 1,
    earlier: list[Script] | None = None,
) -> Script:
    """The beat list for one video: part *part* of *parts* of *topic*.

    *sources* maps each corpus-relative path in ``topic.sources`` to that document's
    markdown. *earlier* holds the scripts already written for this topic, which are shown
    to the model so a later part continues the first instead of repeating it.
    """
    missing = [path for path in topic.sources if path not in sources]
    if missing:
        raise ValueError(f"topic {topic.id} is missing source text for {', '.join(missing)}")
    if not sources:
        raise ValueError(f"topic {topic.id} names no sources; fix topics.json")

    target = target_words(topic.minutes, parts)
    low, high = round(target * (1 - WORD_TOLERANCE)), round(target * (1 + WORD_TOLERANCE))

    lines = [
        f"# Topic {topic.id} - {topic.title}",
        "",
        topic.summary.strip(),
        "",
        f"This is video {part} of {parts} for this topic.",
        f"Aim for about {target} narration words, and stay between {low} and {high}.",
    ]

    for done in earlier or []:
        lines += ["", f"## Already covered by video {done.part} of {parts}: {done.title}", ""]
        lines += [f"- {beat.title}: {beat.narration}" for beat in done.beats]
    if earlier:
        lines += [
            "",
            "Continue from there. Do not re-teach any of it; a one-sentence callback is",
            "welcome, a recap section is not.",
        ]

    budget = SOURCE_BUDGET_CHARS // len(sources)
    lines += ["", "# Source material", ""]
    for path in topic.sources:
        body = sources[path]
        excerpt = body if len(body) <= budget else body[:budget] + TRUNCATED
        lines += ["", f"## Source: {path}", "", excerpt]

    def check(result: Script) -> list[str]:
        problems: list[str] = []
        if len(result.beats) < MIN_BEATS:
            problems.append(f"only {len(result.beats)} beats; a video needs at least {MIN_BEATS}")
        for number, beat in enumerate(result.beats, start=1):
            if not beat.narration.strip():
                problems.append(f"beat {number} ({beat.title!r}) narrates nothing")
            if not beat.on_screen.strip():
                problems.append(f"beat {number} ({beat.title!r}) says nothing about the screen")
            words = len(beat.narration.split())
            if words > MAX_BEAT_WORDS:
                problems.append(
                    f"beat {number} ({beat.title!r}) narrates {words} words, over the "
                    f"{MAX_BEAT_WORDS}-word ceiling. Split it into two beats."
                )
        total = result.words()
        if not low <= total <= high:
            problems.append(
                f"the narration is {total} words across {len(result.beats)} beats; "
                f"this video has to land between {low} and {high} words"
            )
        return problems

    result = ask_valid(INSTRUCTIONS, "\n".join(lines), Script, check)
    return result.model_copy(update={"topic_id": topic.id, "part": part, "parts": parts})
