"""Narration inside a render. Imported by every generated scene.

``from grasp.narration import Narrator`` is the contract the scene prompt promises, so
this name is part of the pipeline's public surface and must not move.
"""

from grasp.narration.narrator import Narrator, Slot, clip_path

__all__ = ["Narrator", "Slot", "clip_path"]
