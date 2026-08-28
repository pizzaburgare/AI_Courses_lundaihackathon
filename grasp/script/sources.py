"""The source material for one topic, as both halves of step 3 send it to a model.

The outline stage and the script stage read the same documents under the same budget, so
the excerpting lives here rather than twice.
"""

SOURCE_BUDGET_CHARS = 150_000  # total across all of a topic's sources
TRUNCATED = "\n\n[... source truncated to fit the context budget ...]"


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
