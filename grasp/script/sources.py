"""The prompt fragments both halves of step 3 send to a model.

The outline stage and the script stage read the same documents under the same budget and
need the same view of the rest of the course, so both live here rather than twice.
"""

from grasp.core import Topic, topic_order

SOURCE_BUDGET_CHARS = 150_000  # total across all of a topic's sources
TRUNCATED = "\n\n[... source truncated to fit the context budget ...]"


def neighbour_block(topic: Topic, neighbours: list[Topic]) -> list[str]:
    """The ``# The rest of the course`` section: what the other topics teach.

    Without this, every topic is planned as though it were the only one, and opens by
    re-deriving its own prerequisites - a viewer working through the course in order sits
    through the definition of a Poisson process once per topic that uses one.
    """
    if not neighbours:
        return []
    here = topic_order(topic.id)
    order = sorted(neighbours, key=lambda t: topic_order(t.id))
    before = [t for t in order if topic_order(t.id) < here]
    after = [t for t in order if topic_order(t.id) > here]

    lines = ["", "# The rest of the course", ""]
    if before:
        lines += [
            "These come before this topic and the viewer has already watched them. Use",
            "their results freely and name them in one clause when you do - but do not",
            "define, derive or re-teach any of it. That is what those videos were for.",
            "",
        ]
        lines += [f"- {t.id} {t.title}: {t.summary.strip()}" for t in before]
    if after:
        lines += [
            "",
            "These come after this topic and are not yours. Do not teach them, and do not",
            "borrow their material to fill time:",
            "",
        ]
        lines += [f"- {t.id} {t.title}: {t.summary.strip()}" for t in after]
    return lines


def source_block(paths: list[str], sources: dict[str, str]) -> list[str]:
    """The ``# Source material`` section, one heading and excerpt per path.

    The budget is split evenly, so one enormous lecture cannot crowd out the exam
    questions that show how the concept is actually used.
    """
    if not sources:
        raise ValueError("no source text to send; fix the topic's sources in topics.json")
    budget = SOURCE_BUDGET_CHARS // len(sources)
    lines = ["", "# Source material", ""]
    for path in paths:
        body = sources[path]
        excerpt = body if len(body) <= budget else body[:budget] + TRUNCATED
        lines += ["", f"## Source: {path}", "", excerpt]
    return lines
