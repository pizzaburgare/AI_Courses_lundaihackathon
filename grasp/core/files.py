"""Where a course keeps its files, and how JSON gets on and off disk.

The only module that knows the layout of a course directory::

    courses/<course>/
        raw/**                        what a human dropped in
        corpus/**.md, corpus/index.json   step 1
        topics.json                       step 2
        videos/<topic_id>-<part>-<slug>/  steps 3-5

There is no state file. The tree is the progress record, so ``grasp status`` reads it and
every step decides what to skip by asking whether its output file exists.
"""

import json
import re
from pathlib import Path

from pydantic import BaseModel

from grasp.core.config import COURSES


def slug(text: str) -> str:
    """Lowercase, hyphen-joined, filesystem-safe. Dots survive, so 2.4 never becomes 24."""
    return re.sub(r"[\s_]+", "-", re.sub(r"[^\w\s.-]", "", text.lower())).strip("-.") or "untitled"


def topic_order(topic_id: str) -> tuple[tuple[int, ...], str]:
    """Sort key for a dotted id, so 2.10 follows 2.9 instead of 2.1."""
    return tuple(int(p) if p.isdigit() else 0 for p in topic_id.split(".")), topic_id


def course_dir(course: str) -> Path:
    """``courses/<course>``, or *course* itself when it already looks like a path."""
    path = Path(course)
    if path.is_dir() or path.is_absolute() or len(path.parts) > 1:
        return path
    return COURSES / course


def video_dir(course: str, topic_id: str, part: int, title: str) -> Path:
    """``<course>/videos/<topic_id>-<part>-<slug>``. One directory holds one video."""
    return course_dir(course) / "videos" / f"{topic_id}-{part}-{slug(title)}"


def video_dirs(course: str, topic_id: str = "", part: int = 0) -> list[Path]:
    """Existing video directories in topic order, optionally narrowed to one topic or part.

    The dot in a topic id is kept in the glob, so asking for ``2.4`` cannot return ``24``.
    """
    pattern = f"{topic_id}-{part or '*'}-*" if topic_id else "*-*-*"
    found = [p for p in (course_dir(course) / "videos").glob(pattern) if p.is_dir()]
    return sorted(found, key=lambda p: (topic_order(p.name.split("-")[0]), p.name))


def read_json[T: BaseModel](path: Path, schema: type[T]) -> T:
    """Load and validate a JSON file an earlier step wrote."""
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist - run the step that writes it first")
    return schema.model_validate_json(path.read_text(encoding="utf-8"))


def write_json(path: Path, model: BaseModel) -> Path:
    """Write a Pydantic model as indented JSON, creating parents. Returns the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
