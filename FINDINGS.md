# Pipeline Stability Findings

Errors discovered during stability analysis, with corresponding fix commits.

| Commit | Error (≤6 words) |
|--------|------------------|
| `5bec7a9` | Manim error not passed to fixer |
| `5bec7a9` | ValueError escapes render loop |
| `5bec7a9` | Structured output parse kills pipeline |
| `5bec7a9` | Fix LLM failure kills whole run |
| `5bec7a9` | Review failure uncaught in loop |
| `156b6b4` | TTS OOM corrupts Manim script |
| `a1537eb` | Fixed batch_size=1 kills TTS perf |
| `a1537eb` | Qwen model reloaded each process |
| `2f683d8` | synthesize_batch hangs with no timeout |
