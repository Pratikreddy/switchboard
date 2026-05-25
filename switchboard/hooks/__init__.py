"""Hook and memory helpers for Switchboard-managed agent prompts."""

from .context import (
    HOOKS_TOOL_VERSION,
    build_context_packet,
    build_hooks_registry,
    build_memory_query,
    build_user_prompt_response,
    default_timeline_db_path,
    discover_existing_hooks,
)
from .timeline import capture_user_prompt, read_timeline_summary

__all__ = [
    "HOOKS_TOOL_VERSION",
    "build_context_packet",
    "build_hooks_registry",
    "build_memory_query",
    "build_user_prompt_response",
    "capture_user_prompt",
    "default_timeline_db_path",
    "discover_existing_hooks",
    "read_timeline_summary",
]
