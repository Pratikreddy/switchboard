"""Benchmark keyword registry helpers for Switchboard brics."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KEYWORD_REGISTRY_SCHEMA = "switchboard-keyword-registry-v0"
KEYWORD_ENTRY_COLUMNS = (
    "label",
    "plain_meaning",
    "bucket_label",
    "similar_bucket_labels",
    "status",
    "human_verified",
    "examples",
    "source_benchmark_ids",
)
KEYWORD_STATUSES = {"pending", "active", "rejected", "parked"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_text(value: str, *, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    lowered = text.lower()
    sensitive_markers = (
        "@",
        "://",
        "\\",
        "secret",
        "credential",
        "password",
        "token",
        "finance row",
        "transcript",
        "raw private",
        "personal data",
        "reasoning trace",
        "chain of thought",
    )
    if any(marker in lowered for marker in sensitive_markers):
        return fallback or "redacted"
    return re.sub(r"\s+", " ", text)[:200]


def _slug(value: str, *, fallback: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "-", _safe_text(value, fallback=fallback).lower()).strip("-")
    return token or fallback


def _stable_id(prefix: str, label: str) -> str:
    slug = _slug(label, fallback="keyword")
    digest = hashlib.sha1(slug.encode("utf-8")).hexdigest()
    serial = int(digest[:6], 16) % 10000
    return f"{prefix}_{slug}_{serial:04d}"


def _split_list(value: str) -> list[str]:
    items = re.split(r"[;,]", str(value or ""))
    return [_safe_text(item) for item in items if _safe_text(item)]


def _parse_bool(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "verified", "human_verified"}


def normalize_keyword_entries(lines: list[str]) -> list[dict[str, Any]]:
    """Parse pipe-delimited benchmark keyword candidate rows.

    Format:
    label | plain_meaning | bucket_label | similar_bucket_labels | status | human_verified | examples | source_benchmark_ids
    """

    entries: list[dict[str, Any]] = []
    for raw in lines:
        payload = raw.strip()
        if payload.startswith("- "):
            payload = payload[2:].strip()
        if not payload or payload.lower().startswith("label |"):
            continue
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) < 6:
            continue
        padded = parts + [""] * (len(KEYWORD_ENTRY_COLUMNS) - len(parts))
        label, plain_meaning, bucket_label, similar_bucket_labels, status, human_verified, examples, source_benchmark_ids = padded[: len(KEYWORD_ENTRY_COLUMNS)]
        safe_status = _slug(status, fallback="pending")
        if safe_status not in KEYWORD_STATUSES:
            safe_status = "pending"
        verified = _parse_bool(human_verified)
        if verified and safe_status == "pending":
            safe_status = "active"
        safe_label = _safe_text(label, fallback="unnamed keyword")
        entries.append(
            {
                "label": safe_label,
                "plain_meaning": _safe_text(plain_meaning, fallback=safe_label),
                "bucket_label": _safe_text(bucket_label, fallback="general"),
                "similar_bucket_labels": _split_list(similar_bucket_labels),
                "status": safe_status,
                "human_verified": verified,
                "examples": _split_list(examples)[:3],
                "source_benchmark_ids": [_slug(item, fallback="source") for item in _split_list(source_benchmark_ids)],
            }
        )
    return entries


def build_keyword_registry(project_root: Path, benchmark_entries: list[dict[str, Any]]) -> dict[str, Any]:
    generated = utc_now_iso()
    normalized: list[dict[str, Any]] = []
    for entry in benchmark_entries:
        if not isinstance(entry, dict):
            continue
        label = _safe_text(str(entry.get("label", "")), fallback="unnamed keyword")
        bucket_label = _safe_text(str(entry.get("bucket_label", "")), fallback="general")
        status = _slug(str(entry.get("status", "pending")), fallback="pending")
        if status not in KEYWORD_STATUSES:
            status = "pending"
        human_verified = bool(entry.get("human_verified", False))
        if human_verified and status == "pending":
            status = "active"
        normalized.append(
            {
                "keyword_id": _stable_id("kw", label),
                "label": label,
                "plain_meaning": _safe_text(str(entry.get("plain_meaning", "")), fallback=label),
                "bucket_label": bucket_label,
                "bucket_id": _stable_id("bucket", bucket_label),
                "similar_bucket_labels": [_safe_text(item) for item in entry.get("similar_bucket_labels", []) if _safe_text(item)],
                "status": status,
                "human_verified": human_verified,
                "examples": [_safe_text(item) for item in entry.get("examples", []) if _safe_text(item)][:3],
                "source_benchmark_ids": [_slug(item, fallback="source") for item in entry.get("source_benchmark_ids", [])],
                "created_at": generated,
                "updated_at": generated,
            }
        )

    bucket_by_id: dict[str, dict[str, Any]] = {}
    for keyword in normalized:
        bucket = bucket_by_id.setdefault(
            keyword["bucket_id"],
            {
                "bucket_id": keyword["bucket_id"],
                "label": keyword["bucket_label"],
                "keyword_count": 0,
                "similar_bucket_ids": [],
            },
        )
        bucket["keyword_count"] += 1
    for keyword in normalized:
        similar_ids = [_stable_id("bucket", label) for label in keyword["similar_bucket_labels"]]
        keyword["similar_bucket_ids"] = similar_ids
        bucket = bucket_by_id[keyword["bucket_id"]]
        bucket["similar_bucket_ids"] = sorted(set([*bucket["similar_bucket_ids"], *similar_ids]))

    keywords = sorted(normalized, key=lambda item: item["keyword_id"])
    buckets = sorted(bucket_by_id.values(), key=lambda item: item["bucket_id"])
    verified_keywords = [item for item in keywords if item["human_verified"]]
    active_keywords = [item for item in keywords if item["human_verified"] and item["status"] == "active"]
    return {
        "generated": generated,
        "schema_version": KEYWORD_REGISTRY_SCHEMA,
        "tool": {
            "name": "switchboard-brics-keyword-registry",
            "package": "switchboard.bricks.keywords",
            "type": "programmatic_python_module",
        },
        "project_root": str(project_root),
        "source": "benchmark keyword fixture entries; no real benchmark dataset ingested",
        "privacy": {
            "classification": "git_safe_metadata",
            "raw_expensive_agent_reasoning": "excluded",
            "raw_private_payloads": "excluded",
            "existing_tags": "candidate_evidence_only",
        },
        "summary": {
            "keyword_count": len(keywords),
            "bucket_count": len(buckets),
            "similar_bucket_count": sum(len(item["similar_bucket_ids"]) for item in buckets),
            "pending_count": sum(1 for item in keywords if item["status"] == "pending"),
            "active_count": len(active_keywords),
            "human_verified_count": len(verified_keywords),
            "rejected_count": sum(1 for item in keywords if item["status"] == "rejected"),
        },
        "id_formats": {
            "keyword_id": "kw_<slug>_<4_digit_serial>",
            "bucket_id": "bucket_<slug>_<4_digit_serial>",
        },
        "keywords": keywords,
        "buckets": buckets,
    }


def export_small_model_packet(keyword_registry: dict[str, Any]) -> dict[str, Any]:
    keywords = [
        {
            "keyword_id": item["keyword_id"],
            "label": item["label"],
            "plain_meaning": item["plain_meaning"],
            "bucket_id": item["bucket_id"],
            "examples": item.get("examples", []),
        }
        for item in keyword_registry.get("keywords", [])
        if item.get("human_verified") and item.get("status") == "active"
    ]
    return {
        "schema_version": "switchboard-small-model-keyword-packet-v0",
        "source_schema": keyword_registry.get("schema_version", ""),
        "rules": [
            "Use only verified keyword IDs.",
            "Use plain meanings and examples; do not infer from expensive-agent notes.",
            "Return keyword IDs, not verbose annotation reasoning.",
        ],
        "keywords": keywords,
    }


def export_simple_keyword_report(keyword_registry: dict[str, Any]) -> str:
    lines = [
        "# Benchmark Keywords",
        "",
        f"- Keywords: {keyword_registry.get('summary', {}).get('keyword_count', 0)}",
        f"- Buckets: {keyword_registry.get('summary', {}).get('bucket_count', 0)}",
        f"- Human verified: {keyword_registry.get('summary', {}).get('human_verified_count', 0)}",
        "",
        "| keyword | meaning | bucket | status | verified | similar buckets |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in keyword_registry.get("keywords", []):
        similar = ", ".join(item.get("similar_bucket_ids", [])) or "none"
        verified = "yes" if item.get("human_verified") else "no"
        lines.append(
            f"| {item.get('label', '')} | {item.get('plain_meaning', '')} | {item.get('bucket_label', '')} | {item.get('status', '')} | {verified} | {similar} |"
        )
    return "\n".join(lines) + "\n"
