"""Every file the pipeline passes between steps. JSON in, JSON out, no parsing.

The field descriptions are the prompt: every model here is handed straight to
``shared.ask_json`` as the response schema, so what a field says is what the model reads.
"""

from pydantic import BaseModel, Field


class Document(BaseModel):
    """One ingested corpus file."""

    path: str = Field(description="Path relative to the corpus directory, e.g. lectures/l4.md")
    summary: str = Field(description="One or two sentences on what this document covers")


class Corpus(BaseModel):
    """``corpus/index.json`` - the whole course, one entry per document."""

    documents: list[Document] = Field(default_factory=list)


class Transcript(BaseModel):
    """One raw file as the model returns it during ingest."""

    summary: str = Field(description="One or two sentences on what this document covers")
    markdown: str = Field(description="The full document transcribed to clean markdown")


class Topic(BaseModel):
    """One concept. Becomes one or more videos."""

    id: str = Field(description="Dotted id, e.g. '2.4'. Prerequisites sort earlier.")
    title: str = Field(description="Short descriptive name of the concept")
    summary: str = Field(description="What a learner should understand after watching")
    sources: list[str] = Field(
        default_factory=list,
        description="Corpus-relative paths of the documents that teach this concept",
    )
    minutes: int = Field(description="Estimated minutes of finished video for this concept")


class Topics(BaseModel):
    """``topics.json`` - the course plan. The cheapest file a human can edit."""

    course: str = Field(default="", description="Course name; leave blank, it is filled in")
    topics: list[Topic] = Field(default_factory=list)


class Beat(BaseModel):
    """One stretch of a video: what is said, and what is on screen while it is said."""

    title: str = Field(description="Three to six words naming this beat")
    section: str = Field(
        default="",
        description="Chapter name when this beat opens a new chapter, otherwise empty",
    )
    narration: str = Field(description="The words spoken, verbatim. Plain prose, no markup.")
    on_screen: str = Field(
        description="What the animation shows and does while this narration plays"
    )


class Script(BaseModel):
    """``script.json`` - one video. The whole interface between steps 3 and 4."""

    title: str = Field(description="Title of this video")
    summary: str = Field(description="One sentence on what this video teaches")
    beats: list[Beat] = Field(default_factory=list)
    topic_id: str = Field(default="", description="Leave blank, it is filled in")
    part: int = Field(default=1, description="Leave blank, it is filled in")
    parts: int = Field(default=1, description="Leave blank, it is filled in")

    def words(self) -> int:
        """Total narration words, which is what decides how long the video runs."""
        return sum(len(beat.narration.split()) for beat in self.beats)


class Chapter(BaseModel):
    """One chapter marker, for YouTube timestamps."""

    name: str
    at: float


class Runtime(BaseModel):
    """``runtime.json`` - what the scene itself observed while it rendered."""

    speech_seconds: float = 0.0
    chapters: list[Chapter] = Field(default_factory=list)


class Check(BaseModel):
    """``check.json`` - everything the free checks found for one video."""

    ok: bool = False
    video_seconds: float = 0.0
    speech_seconds: float = 0.0
    render_error: str = ""
    problems: list[str] = Field(default_factory=list)

    def report(self) -> str:
        """The failure text handed back to the model on a retry."""
        lines = list(self.problems)
        if self.render_error:
            lines.insert(0, f"The render failed:\n{self.render_error}")
        return "\n".join(lines)

    def summary(self) -> str:
        """One line for the operator log."""
        ratio = self.speech_seconds / self.video_seconds if self.video_seconds else 0.0
        return (
            f"{int(self.video_seconds) // 60}m{int(self.video_seconds) % 60:02d}s video, "
            f"{ratio:.0%} narration"
        )
