"""
Post-generation validation of a trial sequence.

Runs BEFORE the scanner trigger. Produces a human-readable report and a
machine-readable dict saved next to the data, so the exact composition
of every run is documented.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

from tasks.utils.pools import counts, max_run_length


@dataclass
class Check:
    """One named verification with its outcome."""
    name: str
    passed: bool
    detail: str = ''

    def line(self) -> str:
        return f"  [{'OK ' if self.passed else 'FAIL'}] {self.name}: {self.detail}"


@dataclass
class ValidationReport:
    """Aggregated checks plus descriptive counts."""
    checks: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def add(self, name: str, passed: bool, detail: str = '') -> None:
        self.checks.append(Check(name, passed, detail))

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict:
        return {
            'all_passed': self.all_passed,
            'checks': [asdict(c) for c in self.checks],
            'summary': self.summary,
        }

    def log(self, logger) -> None:
        head = "SEQUENCE VALIDATION — PASS" if self.all_passed \
            else "SEQUENCE VALIDATION — FAIL"
        (logger.ok if self.all_passed else logger.err)(head)
        for c in self.checks:
            (logger.log if c.passed else logger.err)(c.line())


def check_balanced(report: ValidationReport, name: str, seq: list,
                   tolerance: int = 1) -> None:
    """Assert that all categories occur equally often, +/- tolerance."""
    if not seq:
        report.add(name, True, 'empty')
        return
    c = counts(seq)
    spread = max(c.values()) - min(c.values())
    report.add(
        name, spread <= tolerance,
        f"{c} (spread={spread}, tol={tolerance})",
    )


def check_max_run(report: ValidationReport, name: str, seq: list,
                  max_allowed: int) -> None:
    """Assert that no value repeats more than max_allowed times in a row."""
    longest = max_run_length(seq)
    report.add(
        name, longest <= max_allowed,
        f"longest run = {longest} (max {max_allowed})",
    )


def check_exact(report: ValidationReport, name: str,
                observed, expected) -> None:
    """Assert equality between an observed and an expected value."""
    report.add(name, observed == expected,
               f"observed={observed}, expected={expected}")