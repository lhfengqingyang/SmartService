from app.ai.chunking import chunk_document
from app.config import ChunkingSettings

SETTINGS = ChunkingSettings(target_size=80, max_size=120, overlap_size=15)


def test_markdown_chunks_keep_heading_path_and_indexes() -> None:
    content = """# Refund policy

General refund information.

## Time limit

Customers can request a refund within seven days. This rule applies after delivery.
"""

    chunks = chunk_document(content, ".md", settings=SETTINGS)

    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].heading == "Refund policy"
    assert chunks[-1].heading == "Refund policy > Time limit"
    assert chunks[-1].text.startswith("Refund policy > Time limit\n\n")
    assert all(len(chunk.text) <= SETTINGS.max_size for chunk in chunks)


def test_txt_chunks_overlap_and_preserve_tail() -> None:
    content = "First sentence has useful context. " * 12

    chunks = chunk_document(content, ".txt", settings=SETTINGS)

    assert len(chunks) > 1
    assert chunks[0].text[-SETTINGS.overlap_size :].strip() in chunks[1].text
    assert all(len(chunk.text) <= SETTINGS.max_size for chunk in chunks)


def test_long_paragraph_is_split_without_exceeding_maximum() -> None:
    chunks = chunk_document("x" * 350, ".txt", settings=SETTINGS)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= SETTINGS.max_size for chunk in chunks)


def test_empty_document_returns_no_chunks() -> None:
    assert chunk_document(" \n\n ", ".md", settings=SETTINGS) == []
