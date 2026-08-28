"""``grasp <command> <course> [topic_id]``. Argument parsing, and nothing else.

Every command maps to one function in :mod:`grasp.pipeline`. A step command always does
its work, because you typed it; only ``topic`` and ``course`` skip a step whose output
file already exists. There is no state file - the directory tree is the progress record.
"""

import argparse
import os
import sys
import time
from pathlib import Path

from grasp.core import MODEL_ENV, course_dir, video_dirs
from grasp.pipeline import (
    clock,
    log,
    run_course,
    run_ingest,
    run_render,
    run_scene,
    run_scripts,
    run_topic,
    run_topics,
    status,
)

COLUMNS = (8, 40, 8, 7, 9)


def parse(argv: list[str]) -> argparse.Namespace:
    """The whole command surface. Bad usage exits 2, courtesy of argparse."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default="", help="model for this run; PDFs still use FILE_MODEL")

    parser = argparse.ArgumentParser(prog="grasp", description="Course materials to videos.")
    subs = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_text: str, *, topic: bool = False) -> argparse.ArgumentParser:
        sub = subs.add_parser(name, parents=[common], help=help_text)
        sub.add_argument("course", help="a name under courses/, or a path to a course directory")
        if topic:
            sub.add_argument("topic_id", help="a topic id from topics.json, e.g. 2.4")
        return sub

    add("ingest", "raw material -> a markdown corpus and its index")
    add("topics", "the corpus index -> topics.json")
    scripts = add("script", "one topic -> one script.json per video", topic=True)
    scene = add("scene", "script.json -> scene.py", topic=True)
    render = add("render", "scene.py -> lesson.mp4, retrying on failure", topic=True)
    topic = add("topic", "script -> scene -> render, for every video of one topic", topic=True)
    course = add("course", "every topic in topics.json, in dependency order")
    add("status", "what exists on disk for this course")

    for sub in (scene, render, topic):
        sub.add_argument("--part", type=int, default=0, help="just this part of the topic")
    for sub in (render, topic, course):
        sub.add_argument("--quality", choices=("l", "h"), default="l", help="manim -ql / -qh")
    for sub in (render, topic):
        sub.add_argument("--no-fix", action="store_true", help="render once, call no LLM")
    for sub in (scripts, topic, course):
        sub.add_argument("--force", action="store_true", help="re-run steps whose output exists")
    course.add_argument("--from", dest="start", default="", help="start at this topic id")
    course.add_argument("--only", default="", help="run just these topic ids, comma separated")
    course.add_argument("--jobs", type=int, default=1, help="topics to run in parallel")

    return parser.parse_args(argv)


def videos_for(args: argparse.Namespace) -> list[Path]:
    """The video directories a ``scene`` or ``render`` command addresses."""
    found = video_dirs(args.course, args.topic_id, args.part)
    if not found:
        raise FileNotFoundError(
            f"no videos/{args.topic_id}-* directory in {course_dir(args.course)} - "
            f"run `grasp script {args.course} {args.topic_id}` first"
        )
    return found


def dispatch(args: argparse.Namespace) -> int:
    """Run one command. Returns the process exit code."""
    started = time.time()

    if args.command == "status":
        for row in status(args.course):
            columns = zip(row, COLUMNS, strict=False)
            print("".join(cell[:width].ljust(width) for cell, width in columns) + row[-1])
        return 0

    if args.command == "course":
        return run_course(
            args.course,
            args.quality,
            force=args.force,
            start=args.start,
            only=args.only,
            jobs=args.jobs,
        )

    if args.command == "topic":
        checks = run_topic(
            args.course,
            args.topic_id,
            args.quality,
            fix=not args.no_fix,
            force=args.force,
            part=args.part,
        )
        return 0 if all(check.ok for check in checks) else 1

    if args.command == "ingest":
        run_ingest(args.course)
    elif args.command == "topics":
        run_topics(args.course)
    elif args.command == "script":
        paths = run_scripts(args.course, args.topic_id, force=args.force)
        log("script", "ok", f"{len(paths)} videos, {clock(time.time() - started)}")
    elif args.command == "scene":
        for video in videos_for(args):
            run_scene(video)
            log("scene", "ok", str(video / "scene.py"))
    else:
        checks = [run_render(v, args.quality, fix=not args.no_fix) for v in videos_for(args)]
        return 0 if all(check.ok for check in checks) else 1
    return 0


def main() -> None:
    """``grasp ingest|topics|script|scene|render|topic|course|status``. Exit 0, 1 or 2."""
    args = parse(sys.argv[1:])
    if args.model:
        os.environ[MODEL_ENV] = args.model
    try:
        code = dispatch(args)
    except Exception as err:  # noqa: BLE001 - the CLI boundary reports; run.log holds the rest
        log(args.command, "FAILED", f"{type(err).__name__}: {err}")
        raise SystemExit(1) from None
    raise SystemExit(code)
