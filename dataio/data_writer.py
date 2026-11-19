"""
Incremental TSV writer with atomic final save.

Design goals
------------
crash-safe   : every trial is flushed to disk immediately
no overwrite : reserve each recording exclusively before any trial/sidecar
BIDS-friendly: tab-separated, 'n/a' for missing values,
               stable column order starting with onset/duration/trial_type
verifiable   : row count is re-read and checked after the final save
"""

from __future__ import annotations

import csv
import json
import os
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from dataio.logger import ExperimentLogger

NA = 'n/a'

# Canonical analysis columns first, in the order most scripts expect.
# 'onset' leading also makes the file directly usable as a BIDS
# events.tsv. Any column not listed here keeps its insertion order.
_PREFERRED_ORDER = [
    # The ten columns needed for a standard behavioural analysis
    'subject', 'run', 'trial', 'condition', 'onset',
    'stimulus', 'correct_response', 'response', 'correct', 'RT',
    # BIDS companion
    'duration',
    # Position and provenance
    'task', 'block', 'trial_in_block',
    'design_id', 'design_name', 'paradigm', 'scanner', 'mode',
]


def _order_columns(keys: list[str]) -> list[str]:
    """Preferred columns first, then the rest in insertion order."""
    head = [k for k in _PREFERRED_ORDER if k in keys]
    tail = [k for k in keys if k not in head]
    return head + tail


def _clean(value) -> str:
    """Convert a value to its TSV representation."""
    if value is None or value == '':
        return NA
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, float):
        # Avoid 0.30000000000000004 style artefacts
        return f"{value:.6g}"
    text = str(value)
    # Tabs and newlines would corrupt the file
    return text.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')


class DataWriter:
    """Write trial records to a TSV file, one row per trial."""

    EXT = '.tsv'
    DELIM = '\t'

    def __init__(self, output_dir: Path, filename: str,
                 logger: ExperimentLogger):
        """
        Args:
            output_dir: destination directory (created if needed)
            filename:   stem without extension, reserved exclusively here
            logger:     experiment logger
        """
        self._dir = Path(output_dir)
        self._stem = filename
        self._logger = logger

        self._records: list[dict] = []
        self._headers: list[str] | None = None
        self._file = None
        self._writer = None
        self._path: Path | None = None
        self._n_written = 0
        self._closed = False
        self._reserve()

    # ── Public API ───────────────────────────────────────────────────

    def write_trial(self, record: dict) -> None:
        """Append one trial and flush it to disk immediately."""
        self._records.append(deepcopy(record))

        if self._headers is None:
            self._open(_order_columns(list(record.keys())))

        row = {h: _clean(record.get(h)) for h in self._headers}

        # A new key appearing mid-run would silently be lost: warn once.
        extra = set(record) - set(self._headers)
        if extra:
            self._logger.warn(f"Columns ignored (appeared late): {sorted(extra)}")

        try:
            self._writer.writerow(row)
            self._file.flush()
            os.fsync(self._file.fileno())
            self._n_written += 1
        except Exception as e:
            self._logger.err(f"TSV write error at trial {len(self._records)}: {e}")
            # Stop acquisition rather than silently losing the incremental log.
            # The in-memory record remains available for the final rescue save.
            raise

    def save_final(self, suffix: str = '') -> Path | None:
        """
        Rewrite the complete table atomically and verify the row count.

        Flush a temporary file, then publish it without replacing an existing
        final file. The incremental file remains independent throughout.
        """
        if not self._records:
            self._logger.warn("No trial recorded — nothing to save.")
            return None

        name = f"{self._stem}{suffix}_events{self.EXT}"
        final = self._dir / name
        tmp = final.with_suffix(final.suffix + '.tmp')

        headers = self._headers or _order_columns(list(self._records[0].keys()))

        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            if final.exists():
                raise FileExistsError(f'Données existantes conservées : {final}')
            with open(tmp, 'x', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=headers,
                                   delimiter=self.DELIM,
                                   lineterminator='\n',
                                   extrasaction='ignore')
                w.writeheader()
                for rec in self._records:
                    w.writerow({h: _clean(rec.get(h)) for h in headers})
                f.flush()
                os.fsync(f.fileno())

            self._publish_final(tmp, final)

            n_rows = self._count_rows(final)
            if n_rows == len(self._records):
                self._logger.ok(
                    f"Data saved: {final.name} ({n_rows} trials, verified)"
                )
            else:
                self._logger.err(
                    f"ROW COUNT MISMATCH in {final.name}: "
                    f"{n_rows} on disk vs {len(self._records)} in memory"
                )
            return final

        except Exception as e:
            self._logger.err(f"Final save failed: {e}")
            return None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._file is not None:
            try:
                self._file.flush()
                os.fsync(self._file.fileno())
                self._file.close()
            except Exception:
                pass
            self._file = None

    # ── Properties ───────────────────────────────────────────────────

    @property
    def records(self) -> list[dict]:
        return self._records

    @property
    def n_trials(self) -> int:
        return len(self._records)

    @property
    def filepath(self) -> Path | None:
        return self._path

    # ── Internals ────────────────────────────────────────────────────

    def _reserve(self) -> None:
        """Claim a recording before prepare() can write its design sidecar.

        Keep the marker after close/abort: an interrupted run is still data.
        Exclusive creation also protects two launches of the same run at once.
        """
        self._dir.mkdir(parents=True, exist_ok=True)
        if any(self._dir.glob(f'{self._stem}_*')):
            raise FileExistsError(f'Enregistrement déjà présent : {self._stem}')
        marker = self._dir / f'{self._stem}_reservation.json'
        with marker.open('x', encoding='utf-8') as stream:
            json.dump({'recording': self._stem, 'pid': os.getpid(),
                       'created_utc': datetime.now(timezone.utc).isoformat()}, stream)
            stream.flush()
            os.fsync(stream.fileno())

    def _publish_final(self, tmp: Path, final: Path) -> None:
        try:
            # A same-directory hard link publishes atomically and fails if the
            # destination exists (unlike os.replace on an existing recording).
            os.link(tmp, final)
        except FileExistsError:
            raise
        except OSError:
            # Some scanner USB/network filesystems do not support hard links.
            # Exclusive creation still forbids replacement; tmp + incremental
            # remain intact if copying fails or the process is interrupted.
            with final.open('xb') as target, tmp.open('rb') as source:
                shutil.copyfileobj(source, target)
                target.flush()
                os.fsync(target.fileno())
        tmp.unlink()

    def _open(self, headers: list[str]) -> None:
        self._headers = headers
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / f"{self._stem}_events_incremental{self.EXT}"
        self._file = open(self._path, 'x', newline='', encoding='utf-8')
        self._writer = csv.DictWriter(self._file, fieldnames=headers,
                                      delimiter=self.DELIM,
                                      lineterminator='\n',
                                      extrasaction='ignore')
        self._writer.writeheader()
        self._file.flush()
        self._logger.ok(f"Incremental file: {self._path.name}")

    @staticmethod
    def _count_rows(path: Path) -> int:
        with open(path, 'r', encoding='utf-8') as f:
            return max(0, sum(1 for _ in f) - 1)   # minus header

    def __del__(self):
        self.close()
