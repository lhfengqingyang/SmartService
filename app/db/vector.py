import math
from collections.abc import Sequence


def to_vector_literal(vector: Sequence[float], *, expected_dimensions: int = 1024) -> str:
    if len(vector) != expected_dimensions:
        raise ValueError(f"vector must have {expected_dimensions} dimensions")
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector):
        raise ValueError("vector values must be finite numbers")
    return "[" + ",".join(str(value) for value in vector) + "]"
