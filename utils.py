from __future__ import annotations

from pathlib import Path


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def find_child_text(element, child_name: str, default: str | None = None) -> str | None:
    if element is None:
        return default
    for child in list(element):
        if local_name(child.tag) == child_name:
            return (child.text or "").strip() or default
    return default


def ensure_parent_dir(path: str | Path) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
