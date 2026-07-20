"""Typer CLI: collect, digest, stats, run."""

from __future__ import annotations

import logging

import typer

from . import config, db, digest, pipeline

app = typer.Typer(
    add_completion=False,
    help="Competitive displacement signal monitor for Snowflake.",
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def _db_option() -> str:
    return typer.Option(config.DEFAULT_DB_PATH, "--db", help="SQLite database path.")


@app.command()
def collect(db_path: str = _db_option()) -> None:
    """Run all collectors and store new signals."""
    found, inserted = pipeline.run_collection(db_path)
    typer.echo(f"Collected {found} signals, {inserted} new stored in {db_path}.")


@app.command()
def digest_cmd(
    db_path: str = _db_option(),
    days: int = typer.Option(config.DIGEST_WINDOW_DAYS, "--days", help="Trailing window in days."),
    out_dir: str = typer.Option("digests", "--out", help="Output directory."),
    include_stubs: bool = typer.Option(
        False, "--include-stubs", help="Include stub job signals, tagged [STUB]."
    ),
) -> None:
    """Generate the digest (markdown + HTML) for the trailing window."""
    with db.connect(db_path) as conn:
        md_path, html_path = digest.write_digest(conn, days, out_dir, include_stubs=include_stubs)
    typer.echo(f"Digest written:\n  {md_path}\n  {html_path}")


@app.command()
def stats(db_path: str = _db_option()) -> None:
    """Show signal counts by source, category, and week."""
    with db.connect(db_path) as conn:
        total = db.total_count(conn)
        by_source = db.source_summary(conn)
        by_category = db.counts_by(conn, "category")
        by_week = db.counts_by_week(conn)

    typer.echo(f"Total signals: {total}\n")
    typer.echo("By source:")
    for name, n, last in by_source:
        stamp = last.split(".")[0].replace("T", " ") if last else "never"
        typer.echo(f"  {name:<14} {n:>5}   last: {stamp}")
    typer.echo("\nBy category:")
    for name, n in by_category:
        typer.echo(f"  {name:<22} {n}")
    typer.echo("\nBy week:")
    for wk, n in by_week:
        typer.echo(f"  {wk:<12} {n}")


@app.command()
def run(
    db_path: str = _db_option(),
    days: int = typer.Option(config.DIGEST_WINDOW_DAYS, "--days", help="Trailing window."),
    out_dir: str = typer.Option("digests", "--out", help="Output directory."),
    include_stubs: bool = typer.Option(
        False, "--include-stubs", help="Include stub job signals, tagged [STUB]."
    ),
) -> None:
    """Collect and then generate a digest in one shot."""
    found, inserted = pipeline.run_collection(db_path)
    typer.echo(f"Collected {found} signals, {inserted} new.")
    with db.connect(db_path) as conn:
        md_path, html_path = digest.write_digest(conn, days, out_dir, include_stubs=include_stubs)
    typer.echo(f"Digest written:\n  {md_path}\n  {html_path}")


# Typer derives command names from function names; rename the digest command.
app.registered_commands[1].name = "digest"


def main() -> None:
    app()


if __name__ == "__main__":
    main()
