"""Grasp: course materials in, animated lesson videos out.

Five steps, one folder each, each a function of its inputs::

    grasp.ingest    raw material      -> corpus/**.md + corpus/index.json
    grasp.topics    corpus/index.json -> topics.json
    grasp.script    one topic         -> one or more script.json
    grasp.scene     script.json       -> scene.py
    grasp.render    scene.py          -> lesson.mp4 + check.json

Steps import ``grasp.core`` and nothing else in grasp; they never import each other.
``grasp.pipeline`` is the only module that composes them or writes their output, and
``grasp.cli`` only parses arguments. The exchange format is always JSON validated by a
Pydantic model in ``grasp.core.models``, so no step parses another step's prose.
"""
