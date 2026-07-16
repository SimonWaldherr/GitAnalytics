from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterator, Sequence


CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_now() -> str:
    return utc_now().replace(microsecond=0).isoformat()


def sanitize_text(value: str, replacement: str = "�") -> str:
    return CONTROL_CHARS_RE.sub(replacement, value)


def stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:length]


def hash_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while block := handle.read(1024 * 1024):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in base.items():
        if isinstance(value, dict):
            result[key] = deep_merge(value, {})
        elif isinstance(value, list):
            result[key] = list(value)
        else:
            result[key] = value
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(temporary_name)
        raise


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def relative_display(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
        text = relative.as_posix()
        return text if text != "." else path.name
    except (OSError, ValueError):
        return path.name or str(path)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def slugify(value: str, fallback: str = "item") -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9._-]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-._")
    return normalized or fallback


def human_int(value: int | float | None) -> str:
    if value is None:
        return "–"
    return f"{value:,.0f}".replace(",", ".")


def human_percent(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "–"
    return f"{value * 100:.{digits}f}%".replace(".", ",")


def parse_iso_datetime(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def month_range(start: dt.date, end: dt.date) -> Iterator[tuple[int, int]]:
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1


def longest_streak(days: Sequence[dt.date]) -> tuple[int, dt.date | None, dt.date | None]:
    unique_days = sorted(set(days))
    if not unique_days:
        return 0, None, None
    best_length = current_length = 1
    best_start = best_end = current_start = previous = unique_days[0]
    for day in unique_days[1:]:
        if day == previous + dt.timedelta(days=1):
            current_length += 1
        else:
            current_length = 1
            current_start = day
        if current_length > best_length:
            best_length = current_length
            best_start = current_start
            best_end = day
        previous = day
    return best_length, best_start, best_end


def longest_gap(days: Sequence[dt.date]) -> tuple[int, dt.date | None, dt.date | None]:
    unique_days = sorted(set(days))
    if len(unique_days) < 2:
        return 0, None, None
    left, right = max(zip(unique_days, unique_days[1:]), key=lambda pair: (pair[1] - pair[0]).days)
    return max(0, (right - left).days - 1), left, right


def format_console_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    text_rows = [[str(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in text_rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    head = "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    rule = "  ".join("-" * width for width in widths)
    body = [
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in text_rows
    ]
    return "\n".join([head, rule, *body])
