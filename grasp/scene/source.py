"""Everything the pipeline can learn about a scene file without running it.

``ast`` only: nothing here imports the scene or starts a render, so all of it runs in
milliseconds and catches failures that would otherwise surface as a dead render minutes
later. :mod:`grasp.render` reads narration out of the finished file with the same
functions the check uses, so the check and the renderer cannot disagree about it.
"""

import ast

from grasp.core import Script


def call_name(node: ast.expr) -> str:
    """The trailing identifier of a ``Name`` or ``Attribute`` expression, else empty."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def scene_class(source: str) -> str:
    """The name of the single ``Scene`` subclass in *source*."""
    names = [
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ClassDef)
        and any(call_name(base).endswith("Scene") for base in node.bases)
    ]
    if len(names) != 1:
        raise ValueError(f"expected exactly one Scene subclass, found {len(names)}: {names}")
    return names[0]


def narration_texts(source: str) -> list[str]:
    """The string literal passed to every ``say(...)`` call, in source order.

    The audio for a whole video is pre-synthesised from this list before Manim ever runs,
    which is why anything but a plain literal is an error rather than a silent beat.
    """
    texts: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or call_name(node.func) != "say":
            continue
        first = node.args[0] if node.args else None
        if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
            raise TypeError(
                f"line {node.lineno}: say() takes one plain string literal - no f-strings, "
                "no concatenation, no variables. Its audio is pre-synthesised."
            )
        texts.append(first.value)
    return texts


def check_scene(source: str, script: Script) -> list[str]:
    """Complaints about *source*. Empty means it is ready to render.

    Four things, all static: the file parses, it holds exactly one ``Scene`` subclass with
    one ``construct``, ``finish()`` is that method's last statement, and the narration
    matches ``script.json`` in both directions. The reverse direction matters as much as
    the forward one - without it the word-count band of step 3 is gameable by silently
    dropping beats.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"the file does not parse: {exc}"]

    problems: list[str] = []
    scenes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(call_name(base).endswith("Scene") for base in node.bases)
    ]
    if len(scenes) != 1:
        found = ", ".join(scene.name for scene in scenes) or "none"
        problems.append(f"expected exactly one Scene subclass, found {len(scenes)}: {found}")
    else:
        methods = [
            node
            for node in scenes[0].body
            if isinstance(node, ast.FunctionDef) and node.name == "construct"
        ]
        if len(methods) != 1:
            problems.append(f"{scenes[0].name} must define exactly one construct() method")
        else:
            last = methods[0].body[-1]
            call = last.value if isinstance(last, ast.Expr) else None
            if not isinstance(call, ast.Call) or call_name(call.func) != "finish":
                problems.append(
                    "the last statement in construct() must be narrator.finish(), and "
                    f"nothing may follow it; it is currently {ast.dump(last)[:80]}"
                )

    try:
        said = [" ".join(text.split()) for text in narration_texts(source)]
    except TypeError as exc:
        return [*problems, str(exc)]

    planned = {" ".join(beat.narration.split()): beat.title for beat in script.beats}
    problems.extend(
        "say() narrates text that is not in script.json - narration is copied "
        f"verbatim, never paraphrased or reflowed: {text[:120]!r}"
        for text in said
        if text not in planned
    )
    unsaid = [title for key, title in planned.items() if key not in said]
    if unsaid:
        problems.append(
            f"{len(unsaid)} beats of script.json are never narrated, and every beat needs "
            f"exactly one say() block: {', '.join(unsaid[:5])}"
        )
    return problems
