"""The only module that writes a course's files, and the only one that knows the order.

Every step is a function of its inputs: :func:`grasp.topics.plan_topics` turns a corpus
into topics, :func:`grasp.script.write_script` turns a topic into a script,
:func:`grasp.scene.build_scene` turns a script into Python. None of them touches a course
directory. This is where those functions meet the disk.

Nothing here decides how to teach, transcribe or animate. It reads what the previous step
wrote, calls the next step, writes the answer, and logs one line. The retry policy lives
here too, because "try again with the failure text" is a decision about the pipeline
rather than about Manim.
"""

import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from grasp.core import (
    Check,
    Corpus,
    Document,
    Script,
    Topic,
    Topics,
    course_dir,
    read_json,
    topic_order,
    video_dir,
    video_dirs,
    write_json,
)
from grasp.ingest import MIN_CHARS, SUPPORTED, summarise, transcribe
from grasp.render import render_video
from grasp.scene import build_scene
from grasp.script import part_count, write_script
from grasp.topics import plan_topics

MAX_RENDER_ATTEMPTS = 3


def log(step: str, state: str, detail: str = "", into: Path | None = None) -> None:
    """One line of operator output: ``HH:MM:SS step state detail``. No banner, no spinner."""
    now = datetime.now(UTC).astimezone()  # aware, but still the operator's wall clock
    line = f"{now.strftime('%H:%M:%S')} {step:<7} {state:<7} {detail}".rstrip()
    print(line, flush=True)
    if into is not None:
        into.parent.mkdir(parents=True, exist_ok=True)
        with into.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def clock(seconds: float) -> str:
    """``3m07s``. Used everywhere a duration is printed."""
    return f"{int(seconds) // 60}m{int(seconds) % 60:02d}s"


def find_topic(course: str, topic_id: str) -> Topic:
    """The one topic in ``topics.json`` with this id."""
    topics = read_json(course_dir(course) / "topics.json", Topics)
    for topic in topics.topics:
        if topic.id == topic_id:
            return topic
    known = ", ".join(t.id for t in topics.topics) or "none"
    raise ValueError(f"no topic {topic_id!r} in {course}'s topics.json (have: {known})")


def run_ingest(course: str) -> Path:
    """``raw/**`` -> ``corpus/**.md`` + ``corpus/index.json``. Returns the index path.

    A file whose markdown already exists and is long enough is reused, and its summary is
    taken from the old index rather than re-generated, so re-running after adding one
    lecture costs one document instead of the whole course.
    """
    root = course_dir(course)
    raw, corpus = root / "raw", root / "corpus"
    if not raw.is_dir():
        raise FileNotFoundError(f"{raw} does not exist - put the course material there first")

    index = corpus / "index.json"
    known = (
        {d.path: d.summary for d in read_json(index, Corpus).documents} if index.is_file() else {}
    )
    documents: list[Document] = []

    for source in sorted(path for path in raw.rglob("*") if path.is_file()):
        if source.suffix.lower() not in SUPPORTED:
            log("ingest", "skip", f"{source.relative_to(raw)} is not a supported file type")
            continue

        dest = corpus / source.relative_to(raw).with_suffix(".md")
        relative = dest.relative_to(corpus).as_posix()
        existing = dest.read_text(encoding="utf-8", errors="replace") if dest.is_file() else ""

        if len(existing) >= MIN_CHARS:
            summary = known.get(relative) or summarise(existing)
            documents.append(Document(path=relative, summary=summary))
            log("ingest", "reuse", relative)
            continue

        result = transcribe(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(result.markdown, encoding="utf-8")
        documents.append(Document(path=relative, summary=result.summary))
        log("ingest", "ok", f"{relative}, {len(result.markdown):,} chars")

    if not documents:
        raise ValueError(f"nothing under {raw} could be ingested")
    log("ingest", "ok", f"{len(documents)} documents in {index}")
    return write_json(index, Corpus(documents=documents))


def run_topics(course: str) -> Path:
    """``corpus/index.json`` -> ``topics.json``. Returns the path written."""
    root = course_dir(course)
    topics = plan_topics(root.name, read_json(root / "corpus" / "index.json", Corpus))
    path = write_json(root / "topics.json", topics)
    minutes = sum(topic.minutes for topic in topics.topics)
    videos = sum(part_count(topic.minutes) for topic in topics.topics)
    log("topics", "ok", f"{len(topics.topics)} topics, {videos} videos, {minutes} minutes")
    return path


def run_scripts(course: str, topic_id: str, *, force: bool = False) -> list[Path]:
    """One topic -> one ``script.json`` per video. Returns their paths, in playing order.

    The parts are written one at a time, each with the earlier ones in front of it, which
    is what stops video 2 from re-teaching video 1. A part that already exists is loaded
    rather than rewritten - and still shown to the next part.
    """
    root = course_dir(course)
    topic = find_topic(course, topic_id)
    sources: dict[str, str] = {}
    for relative in topic.sources:
        path = root / "corpus" / relative
        if not path.is_file():
            raise FileNotFoundError(
                f"topic {topic.id} names a source that is not in the corpus: {path}"
            )
        sources[relative] = path.read_text(encoding="utf-8", errors="replace")

    parts = part_count(topic.minutes)
    written: list[Path] = []
    earlier: list[Script] = []
    for part in range(1, parts + 1):
        video = video_dir(course, topic.id, part, topic.title)
        path = video / "script.json"
        if path.is_file() and not force:
            script = read_json(path, Script)
            log("script", "skip", f"{path} exists", into=video / "run.log")
        else:
            script = write_script(topic, sources, part, parts, earlier)
            write_json(path, script)
            log(
                "script",
                "ok",
                f"{path}, {len(script.beats)} beats, {script.words()} words",
                into=video / "run.log",
            )
        earlier.append(script)
        written.append(path)
    return written


def run_scene(video: Path, failure: str = "") -> Path:
    """``script.json`` -> ``scene.py`` in the same directory. Returns its path."""
    source = build_scene(read_json(video / "script.json", Script), failure)
    path = video / "scene.py"
    path.write_text(source, encoding="utf-8")
    return path


def run_render(video: Path, quality: str = "l", *, fix: bool = True) -> Check:
    """Render one video, rewriting ``scene.py`` from the failures until it passes.

    Draft quality is used for every attempt: a check that fails at ``-ql`` fails at
    ``-qh`` too, and it fails in a tenth of the time. Only a video that passed is
    re-rendered at the quality that was asked for. With ``fix=False`` this renders exactly
    once and makes no LLM call, which is the mode to sit in while hand-editing a scene.
    """
    log_file = video / "run.log"
    attempts = MAX_RENDER_ATTEMPTS if fix else 1
    check = Check()
    for attempt in range(1, attempts + 1):
        check = render_video(video, "l")
        write_json(video / "check.json", check)
        if check.ok or not fix:
            break
        first = next((line for line in check.report().splitlines() if line.strip()), "failed")
        log("render", f"{attempt}/{attempts}", first, into=log_file)
        if attempt < attempts:
            run_scene(video, failure=check.report())

    if check.ok and quality != "l":
        check = render_video(video, quality)
        write_json(video / "check.json", check)
    log("render", "ok" if check.ok else "flagged", check.summary(), into=log_file)
    return check


def run_topic(
    course: str,
    topic_id: str,
    quality: str = "l",
    *,
    fix: bool = True,
    force: bool = False,
    part: int = 0,
) -> list[Check]:
    """Script -> scene -> render for every video of one topic.

    A step whose output file already exists is skipped, so re-running after a crash picks
    up where it stopped. ``--force`` runs all of them anyway.
    """
    started = time.time()
    scripts = run_scripts(course, topic_id, force=force)
    checks: list[Check] = []

    for path in scripts:
        video = path.parent
        if part and read_json(path, Script).part != part:
            continue
        log_file = video / "run.log"

        if force or not (video / "scene.py").is_file():
            step = time.time()
            run_scene(video)
            log("scene", "ok", f"scene.py, {clock(time.time() - step)}", into=log_file)
        else:
            log("scene", "skip", "scene.py exists", into=log_file)

        if force or not (video / "lesson.mp4").is_file():
            checks.append(run_render(video, quality, fix=fix))
        else:
            check = video / "check.json"
            checks.append(read_json(check, Check) if check.is_file() else Check(ok=True))
            log("render", "skip", "lesson.mp4 exists", into=log_file)

    log("topic", "ok", f"{topic_id}, {len(checks)} videos, {clock(time.time() - started)}")
    return checks


def run_course(
    course: str,
    quality: str = "l",
    *,
    force: bool = False,
    start: str = "",
    only: str = "",
    jobs: int = 1,
) -> int:
    """Every topic, in dependency order. One bad topic never stops the rest.

    Returns the process exit code: 1 if any topic failed, 0 otherwise. A failure leaves a
    ``FAILED`` file and a traceback in the topic's videos, so the tree still says what
    happened after the terminal has scrolled away.
    """
    topics = read_json(course_dir(course) / "topics.json", Topics).topics
    if only:
        wanted = {i.strip() for i in only.split(",") if i.strip()}
        topics = [t for t in topics if t.id in wanted]
    if start:
        topics = [t for t in topics if topic_order(t.id) >= topic_order(start)]
    topics = sorted(topics, key=lambda t: topic_order(t.id))

    planned = sum(part_count(topic.minutes) for topic in topics)
    log("course", "ok", f"{len(topics)} topics, {planned} videos")
    started = time.time()
    failed: list[str] = []

    def one(topic: Topic) -> None:
        # pylint: disable=broad-exception-caught
        try:
            run_topic(course, topic.id, quality, fix=True, force=force)
        except Exception as err:  # noqa: BLE001 - one bad topic must not stop the course
            failed.append(topic.id)
            reason = f"{type(err).__name__}: {err}"
            for video in video_dirs(course, topic.id) or [video_dir(course, topic.id, 1, "")]:
                video.mkdir(parents=True, exist_ok=True)
                (video / "FAILED").write_text(reason + "\n", encoding="utf-8")
                with (video / "run.log").open("a", encoding="utf-8") as handle:
                    handle.write(traceback.format_exc())
            log(topic.id, "FAILED", reason)

    if jobs > 1:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(one, topics))
    else:
        for topic in topics:
            one(topic)

    done = len(topics) - len(failed)
    log(
        "course",
        "FAILED" if failed else "ok",
        f"{done} ok, {len(failed)} failed, {clock(time.time() - started)}",
    )
    return 1 if failed else 0


def status(course: str) -> list[tuple[str, ...]]:
    """One row per video directory, derived entirely from the tree. Runs nothing."""
    rows: list[tuple[str, ...]] = [("video", "title", "script", "scene", "length", "checks")]
    for video in video_dirs(course):
        topic_id, part, title = video.name.split("-", 2)
        report = (
            read_json(video / "check.json", Check) if (video / "check.json").is_file() else None
        )
        if (video / "FAILED").is_file():
            verdict = "FAILED"
        elif report is None:
            verdict = "-"
        elif report.ok:
            verdict = "clean"
        else:
            verdict = f"{len(report.violations) + len(report.problems)} flagged"
        rows.append((
            f"{topic_id}.{part}",
            title,
            "ok" if (video / "script.json").is_file() else "-",
            "ok" if (video / "scene.py").is_file() else "-",
            clock(report.video_seconds) if report and (video / "lesson.mp4").is_file() else "-",
            verdict,
        ))
    return rows
