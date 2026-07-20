"""Weekly digest generation in Markdown and styled HTML."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import classifier, db
from .models import Signal
from .scoring import normalize_company

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

# High-score threshold that earns a tailored outreach angle.
HIGH_SCORE_THRESHOLD = 55

# Category -> outreach angle. Template-based, no generation at runtime.
OUTREACH_ANGLES: dict[str, str] = {
    classifier.MIGRATION_INTENT: (
        "Migration already in motion. Lead with a migration accelerator and a "
        "side-by-side reference architecture; offer a scoped proof-of-concept "
        "with a fixed-timeline cutover plan."
    ),
    classifier.COST_PAIN: (
        "Cost is the wedge. Open with a TCO comparison and a workload-level "
        "credit-burn teardown; quantify projected savings before asking for a "
        "meeting."
    ),
    classifier.PERFORMANCE_COMPLAINT: (
        "Performance frustration. Lead with a benchmark on their query shape "
        "(concurrency, large scans) and a tuning review that reframes the "
        "warehouse-scaling spend."
    ),
    classifier.VENDOR_COMPARISON: (
        "Actively evaluating alternatives. Send a neutral bake-off guide and "
        "offer to run their real workloads head-to-head; be the vendor that "
        "makes the comparison easy."
    ),
    classifier.OTHER: (
        "Early-stage signal. Nurture with relevant content and monitor for a "
        "sharper cost or migration trigger before direct outreach."
    ),
}


@dataclass(slots=True)
class DigestData:
    """Everything a digest template needs."""

    generated_at: datetime
    window_days: int
    total_signals: int
    prior_signals: int
    top_signals: list[Signal]
    by_category: dict[str, list[Signal]]
    new_companies: list[str]
    outreach: list[tuple[Signal, str]]
    source_counts: list[tuple[str, int]]

    @property
    def trend_delta(self) -> int:
        return self.total_signals - self.prior_signals

    @property
    def trend_label(self) -> str:
        delta = self.trend_delta
        arrow = "+" if delta > 0 else ""
        return f"{self.total_signals} this period vs {self.prior_signals} prior ({arrow}{delta})"


def _outreach_angle(signal: Signal) -> str:
    return OUTREACH_ANGLES.get(signal.category or classifier.OTHER, OUTREACH_ANGLES[classifier.OTHER])


def build_digest_data(conn, window_days: int) -> DigestData:
    """Assemble digest sections from the trailing window of signals."""
    signals = db.signals_since(conn, window_days)

    by_category: dict[str, list[Signal]] = {c: [] for c in classifier.CATEGORIES}
    for sig in signals:
        by_category.setdefault(sig.category or classifier.OTHER, []).append(sig)
    by_category = {c: rows for c, rows in by_category.items() if rows}

    displacement = [s for s in signals if s.category in classifier.DISPLACEMENT_CATEGORIES]

    known = {normalize_company(c) for c in db.known_companies_before(conn, window_days)}
    new_companies: list[str] = []
    seen_normalized: set[str] = set()
    for sig in signals:
        if not sig.company:
            continue
        norm = normalize_company(sig.company)
        if norm in known or norm in seen_normalized:
            continue
        seen_normalized.add(norm)
        new_companies.append(sig.company)

    outreach = [
        (sig, _outreach_angle(sig))
        for sig in displacement
        if sig.score >= HIGH_SCORE_THRESHOLD
    ]

    return DigestData(
        generated_at=datetime.now(timezone.utc),
        window_days=window_days,
        total_signals=len(signals),
        prior_signals=db.count_posted_between(conn, window_days * 2, window_days),
        top_signals=displacement[:15],
        by_category=by_category,
        new_companies=new_companies,
        outreach=outreach,
        source_counts=db.counts_by(conn, "source"),
    )


def _environment(trim: bool) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=trim,
        lstrip_blocks=trim,
    )


def render_markdown(data: DigestData) -> str:
    # Markdown is newline-sensitive; block trimming would fuse list items.
    return _environment(trim=False).get_template("digest.md.j2").render(d=data)


def render_html(data: DigestData) -> str:
    return _environment(trim=True).get_template("digest.html.j2").render(d=data)


def write_digest(conn, window_days: int, out_dir: str) -> tuple[Path, Path]:
    """Render both formats to ``out_dir`` and return (markdown_path, html_path)."""
    data = build_digest_data(conn, window_days)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = data.generated_at.strftime("%Y%m%d")
    md_path = out / f"digest-{stamp}.md"
    html_path = out / f"digest-{stamp}.html"
    md_path.write_text(render_markdown(data), encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    return md_path, html_path
