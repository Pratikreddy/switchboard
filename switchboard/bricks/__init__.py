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
from .keywords import (
    KEYWORD_ENTRY_COLUMNS,
    KEYWORD_REGISTRY_SCHEMA,
    build_keyword_registry,
    export_simple_keyword_report,
    export_small_model_packet,
    normalize_keyword_entries,
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
    "KEYWORD_ENTRY_COLUMNS",
    "KEYWORD_REGISTRY_SCHEMA",
    "build_keyword_registry",
    "export_simple_keyword_report",
    "export_small_model_packet",
    "normalize_keyword_entries",
]
