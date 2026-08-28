"""Step 2: the corpus index -> the topic list.

The input is the index step 1 wrote - one summary line per file - not the documents
themselves, so a 300-file course costs a few thousand tokens instead of overflowing the
context in alphabetical order.

Data in, data out. ``topics.json`` is the cheapest place a human can change the shape of
a whole course, so the write is left to :mod:`grasp.pipeline` and this function can be
run, inspected and re-run without a course directory in sight.
"""

from pathlib import Path

from grasp.core import LANGUAGE_RULE, Corpus, Topics, ask_valid

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
INSTRUCTIONS = PROMPT + "\n" + LANGUAGE_RULE

MIN_MINUTES, MAX_MINUTES = 3, 45  # per topic; longer than this is two concepts, not one


def plan_topics(course: str, corpus: Corpus) -> Topics:
    """Turn *corpus* into an ordered topic list for *course*.

    Every topic must name at least one source that exists in the index: step 3 does no
    retrieval of its own, so a topic with no sources or an invented path is a topic that
    can never become a video.
    """
    if not corpus.documents:
        raise ValueError("the corpus index lists no documents - run `grasp ingest` first")

    known = {document.path for document in corpus.documents}
    listing = "\n".join(f"{d.path}\n    {d.summary}" for d in corpus.documents)
    request = (
        f"# Course: {course}\n\n"
        f"## Corpus index, {len(corpus.documents)} documents\n\n"
        f"Each entry is a corpus-relative path and what that document covers.\n\n"
        f"{listing}\n"
    )

    def check(result: Topics) -> list[str]:
        problems: list[str] = []
        if not result.topics:
            return ["no topics were produced"]
        seen: set[str] = set()
        for topic in result.topics:
            label = f"topic {topic.id!r}"
            if topic.id in seen:
                problems.append(f"{label} appears twice; ids must be unique")
            seen.add(topic.id)
            if not topic.title.strip() or not topic.summary.strip():
                problems.append(f"{label} is missing a title or a summary")
            if not topic.sources:
                problems.append(f"{label} names no sources; every topic needs at least one")
            invented = [s for s in topic.sources if s not in known]
            if invented:
                problems.append(
                    f"{label} names sources that are not in the corpus index: "
                    f"{', '.join(invented)}. Copy paths exactly as listed."
                )
            if not MIN_MINUTES <= topic.minutes <= MAX_MINUTES:
                problems.append(
                    f"{label} estimates {topic.minutes} minutes; the range is "
                    f"{MIN_MINUTES}-{MAX_MINUTES}. Split anything bigger into two topics."
                )
        return problems

    result = ask_valid(INSTRUCTIONS, request, Topics, check)
    return Topics(course=course, topics=result.topics)
