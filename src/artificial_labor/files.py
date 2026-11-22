"""Turn files into short text previews the LLM can read."""

from __future__ import annotations

import csv
import io
from pathlib import Path

TEXT_SUFFIXES = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".sql", ".html", ".htm", ".css", ".js",
    ".py", ".xml", ".yaml", ".yml", ".php", ".log", ".ini",
}  # fmt: skip


def list_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file())


def preview(path: Path, limit: int = 2500) -> str:
    """Best-effort human-readable preview of a file, truncated to `limit` chars."""
    suffix = path.suffix.lower()
    try:
        if suffix in {".csv", ".tsv"}:
            text = _preview_table(path, limit)
        elif suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
        elif suffix in {".xlsx", ".xlsm"}:
            text = _preview_xlsx(path)
        elif suffix == ".docx":
            text = _preview_docx(path)
        elif suffix == ".pdf":
            text = _preview_pdf(path)
        else:
            return f"<binary {suffix or 'file'}, {path.stat().st_size} bytes>"
    except Exception as e:  # previews must never break the pipeline
        return f"<could not read: {e}>"
    if len(text) > limit:
        text = text[:limit] + f"\n... <truncated, {len(text)} chars total>"
    return text


def _preview_table(path: Path, limit: int) -> str:
    """Raw head of the file plus a column profile, so truncation doesn't hide the data's shape."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    if len(raw) <= limit:
        return raw
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    rows = list(csv.reader(io.StringIO(raw), delimiter=delimiter))
    if not rows:
        return raw
    header, body = rows[0], rows[1:]
    profile = [f"{len(body)} data rows, {len(header)} columns. Column profile:"]
    for i, name in enumerate(header):
        values = [r[i] for r in body if i < len(r)]
        distinct = list(dict.fromkeys(values))
        sample = ", ".join(distinct[:20]) + (" ..." if len(distinct) > 20 else "")
        profile.append(f"- {name}: {len(distinct)} distinct: {sample}")
    summary = "\n".join(profile)[: limit // 2]
    return f"{summary}\n\nFirst rows:\n{raw[: limit - len(summary)]}"


def _preview_xlsx(path: Path) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(path)  # formulas, not cached values: generated files have none
    out = []
    for ws in wb.worksheets:
        out.append(f"## sheet {ws.title!r} ({ws.max_row} rows x {ws.max_column} cols)")
        if ws.data_validations.dataValidation:
            out.append(f"data validations: {len(ws.data_validations.dataValidation)}")
        for row in ws.iter_rows(max_row=15, values_only=True):
            out.append(" | ".join("" if v is None else str(v) for v in row))
    return "\n".join(out)


def _preview_docx(path: Path) -> str:
    import docx

    d = docx.Document(str(path))
    out = [p.text for p in d.paragraphs if p.text.strip()]
    for i, table in enumerate(d.tables):
        out.append(f"## table {i + 1}")
        out += [" | ".join(c.text for c in row.cells) for row in table.rows[:15]]
    return "\n".join(out)


def _preview_pdf(path: Path) -> str:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        pages = [f"## page {i + 1}\n{p.extract_text() or ''}" for i, p in enumerate(pdf.pages[:3])]
        return f"{len(pdf.pages)} pages\n" + "\n".join(pages)


def describe(files: list[Path], root: Path, limit: int = 2500) -> str:
    if not files:
        return "(none)"
    parts = []
    for f in files:
        rel = f.relative_to(root)
        parts.append(f"### {rel} ({f.stat().st_size} bytes)\n{preview(f, limit)}")
    return "\n\n".join(parts)
