"""Switchboard brick contracts and deterministic registry builders."""

from .registry import (
    BENCHMARK_KEYWORD_CONTRACT,
    BENCHMARK_KEYWORD_RULES,
    BRICK_CONTRACT,
    BRICK_ENTRY_COLUMNS,
    SEEDED_SWITCHBOARD_BRICKS,
    SUITE_BRICK_RULES,
    build_brick_registry,
    normalize_brick_lines,
)

__all__ = [
    "BRICK_CONTRACT",
    "BENCHMARK_KEYWORD_CONTRACT",
    "BENCHMARK_KEYWORD_RULES",
    "BRICK_ENTRY_COLUMNS",
    "SEEDED_SWITCHBOARD_BRICKS",
    "SUITE_BRICK_RULES",
    "build_brick_registry",
    "normalize_brick_lines",
]
