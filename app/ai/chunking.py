import re
from dataclasses import dataclass

from app.config import ChunkingSettings, get_chunking_settings

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FENCED_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)
_SENTENCE_ENDINGS = frozenset("\u3002\uff01\uff1f\uff1b.!?;")


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    heading: str | None


def chunk_document(
    content: str,
    file_type: str,
    *,
    settings: ChunkingSettings | None = None,
) -> list[TextChunk]:
    if file_type not in {".md", ".txt"}:
        raise ValueError("file_type must be .md or .txt")

    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    settings = settings or get_chunking_settings()
    sections = _markdown_sections(normalized) if file_type == ".md" else [(None, normalized)]
    chunks: list[TextChunk] = []

    for heading, body in sections:
        prefix = f"{heading}\n\n" if heading else ""
        body_max = max(1, settings.max_size - len(prefix))
        body_target = max(1, min(settings.target_size - len(prefix), body_max))
        body_overlap = min(settings.overlap_size, max(0, body_target - 1))

        for part in _split_text(body, body_target, body_max, body_overlap):
            chunks.append(TextChunk(index=len(chunks), text=f"{prefix}{part}", heading=heading))

    return chunks


def _markdown_sections(content: str) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, str]] = []
    heading_stack: list[str] = []
    body_lines: list[str] = []
    current_heading: str | None = None
    in_fence = False

    def flush() -> None:
        body = "\n".join(body_lines).strip()
        if body:
            sections.append((current_heading, body))

    for line in content.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence

        match = None if in_fence else _HEADING_PATTERN.match(line)
        if not match:
            body_lines.append(line)
            continue

        flush()
        body_lines = []
        level = len(match.group(1))
        title = match.group(2).strip()
        heading_stack[level - 1 :] = [title]
        current_heading = " > ".join(heading_stack)

    flush()
    return sections


def _split_text(text: str, target: int, maximum: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []

    protected_ranges = [(match.start(), match.end()) for match in _FENCED_BLOCK_PATTERN.finditer(text)]
    parts: list[str] = []
    start = 0

    while start < len(text):
        if len(text) - start <= maximum:
            end = len(text)
        else:
            target_end = min(start + target, len(text))
            hard_end = min(start + maximum, len(text))
            minimum_end = min(start + max(1, target // 2), target_end)
            candidates = _boundary_candidates(text, minimum_end, hard_end, protected_ranges)
            before_target = [position for position in candidates if position <= target_end]
            end = before_target[-1] if before_target else (candidates[0] if candidates else target_end)

        part = text[start:end].strip()
        if part:
            parts.append(part)
        if end >= len(text):
            break

        next_start = max(end - overlap, start + 1)
        while next_start < end and text[next_start].isspace():
            next_start += 1
        start = next_start

    return parts


def _boundary_candidates(
    text: str,
    start: int,
    end: int,
    protected_ranges: list[tuple[int, int]],
) -> list[int]:
    candidates: list[int] = []
    for index in range(start, end):
        if any(range_start < index < range_end for range_start, range_end in protected_ranges):
            continue
        if text[index] in _SENTENCE_ENDINGS or text[index] == "\n":
            candidates.append(index + 1)
    return candidates
