"""Step 1, one file at a time: any supported raw file -> markdown plus a one-line summary.

A path in, a :class:`Transcript` out. Nothing is written here - the walk over ``raw/**``
and every write into ``corpus/`` lives in :mod:`grasp.pipeline`, so this module can be
called on a single file from a REPL without touching a course directory.
"""

import base64
import io
import tempfile
from pathlib import Path

from PIL import Image

from grasp.core import FILE_MODEL, Transcript, ask, ask_json

INSTRUCTIONS = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")

TEXT = frozenset({".md", ".txt", ".markdown", ".rst"})
PDF = frozenset({".pdf"})
IMAGES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"})
VIDEOS = frozenset({".mp4", ".mov", ".mkv", ".webm"})
SUPPORTED = TEXT | PDF | IMAGES | VIDEOS

MIN_CHARS = 200  # shorter than this and the transcription silently failed
MAX_IMAGE_PIXELS = 1920
SUMMARY_SAMPLE_CHARS = 20_000
WHISPER_MODEL = "large-v3"


def summarise(body: str) -> str:
    """One or two sentences on *body*, for the corpus index."""
    return ask(
        INSTRUCTIONS,
        f"Summarise this document in one or two sentences:\n\n{body[:SUMMARY_SAMPLE_CHARS]}",
    )


def transcribe(source: Path) -> Transcript:
    """Read *source* and return its markdown and summary.

    Text files are copied verbatim and cost one summary call. A PDF or an image is sent
    to the model as content parts and comes back as one structured answer. Video is
    transcribed locally by Whisper, then summarised.
    """
    suffix = source.suffix.lower()

    if suffix in TEXT:
        body = source.read_text(encoding="utf-8", errors="replace")
        result = Transcript(summary=summarise(body), markdown=body)

    elif suffix in PDF:
        data = base64.standard_b64encode(source.read_bytes()).decode()
        result = ask_json(
            INSTRUCTIONS,
            [
                {
                    "type": "file",
                    "file": {
                        "filename": source.name,
                        "file_data": f"data:application/pdf;base64,{data}",
                    },
                },
                {"type": "text", "text": "Transcribe this document."},
            ],
            Transcript,
            FILE_MODEL,
        )

    elif suffix in IMAGES:
        image = Image.open(source).convert("RGB")
        image.thumbnail((MAX_IMAGE_PIXELS, MAX_IMAGE_PIXELS), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        data = base64.standard_b64encode(buffer.getvalue()).decode()
        result = ask_json(
            INSTRUCTIONS,
            [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}},
                {"type": "text", "text": "Transcribe this image."},
            ],
            Transcript,
            FILE_MODEL,
        )

    elif suffix in VIDEOS:
        import whisper
        from moviepy import VideoFileClip

        with tempfile.NamedTemporaryFile(suffix=".mp3") as audio:
            clip = VideoFileClip(str(source))
            if clip.audio is None:
                clip.close()
                raise ValueError(f"{source} has no audio track to transcribe")
            clip.audio.write_audiofile(audio.name, logger=None)
            clip.close()
            spoken = whisper.load_model(WHISPER_MODEL).transcribe(audio.name)
        body = str(spoken["text"]).strip()
        result = Transcript(summary=summarise(body), markdown=body)

    else:
        raise ValueError(f"{source}: unsupported file type {suffix!r}")

    if len(result.markdown) < MIN_CHARS:
        raise ValueError(
            f"{source} produced only {len(result.markdown)} characters of markdown; "
            f"anything under {MIN_CHARS} means the transcription failed"
        )
    return result
