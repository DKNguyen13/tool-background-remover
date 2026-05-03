"""
dataset/manager.py
Batch dataset management: scan folders, track status, generate reports.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from enum import Enum


class Status(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class FileRecord:
    path: str
    status: Status = Status.PENDING
    output_path: str = ""
    input_size: int = 0
    output_size: int = 0
    error: str = ""
    elapsed_ms: int = 0

    @property
    def compression_ratio(self) -> float:
        if self.input_size == 0:
            return 0.0
        return 1 - self.output_size / self.input_size


@dataclass
class Dataset:
    records: list[FileRecord] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # ── Statistics ────────────────────────────────────────────────────────────

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def done(self) -> int:
        return sum(1 for r in self.records if r.status == Status.DONE)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.records if r.status == Status.ERROR)

    @property
    def pending(self) -> int:
        return sum(1 for r in self.records if r.status == Status.PENDING)

    def summary(self) -> str:
        saved = sum(r.input_size - r.output_size for r in self.records if r.status == Status.DONE)
        return (
            f"Total: {self.total} | Done: {self.done} | "
            f"Errors: {self.errors} | Saved: {_fmt_bytes(saved)}"
        )

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: Path):
        path = Path(path)
        path.write_text(json.dumps(
            {"created_at": self.created_at, "records": [asdict(r) for r in self.records]},
            indent=2,
        ))

    @classmethod
    def load(cls, path: Path) -> "Dataset":
        data = json.loads(Path(path).read_text())
        records = [FileRecord(**r) for r in data.get("records", [])]
        return cls(records=records, created_at=data.get("created_at", ""))


def scan_folder(folder: Path, extensions=(".png", ".jpg", ".jpeg", ".webp")) -> Dataset:
    files = sorted(p for p in Path(folder).rglob("*") if p.suffix.lower() in extensions)
    records = [FileRecord(path=str(f), input_size=f.stat().st_size) for f in files]
    return Dataset(records=records)


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
