from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from docx import Document
from openpyxl import load_workbook

from .models import EvidenceRef


@lru_cache(maxsize=256)
def file_sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative_name(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def decode_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold().strip()


def parse_decimal(value: object) -> Decimal:
    text = str(value or "").strip().replace("\u00a0", "").replace("€", "")
    if not text:
        return Decimal("0")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Cannot parse decimal value: {value!r}") from exc


def parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for pattern in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class SourceRow:
    source: Path
    root: Path
    row_number: int
    data: dict[str, str]
    raw: str
    sheet: str | None = None
    cells: dict[str, str] | None = None

    def evidence(self, *columns: str, query: str | None = None) -> EvidenceRef:
        excerpt = "; ".join(f"{column}={self.data.get(column, '')}" for column in columns)
        return EvidenceRef(
            document=relative_name(self.source, self.root),
            locator_type="cell" if self.sheet else "row",
            row=self.row_number,
            columns=list(columns),
            sheet=self.sheet,
            cell_range=self._cell_range(columns),
            excerpt=excerpt or self.raw[:500],
            query=query,
            sha256=file_sha256(str(self.source)),
        )

    def _cell_range(self, columns: Iterable[str]) -> str | None:
        if not self.cells:
            return None
        selected = [self.cells[column] for column in columns if column in self.cells]
        return ",".join(selected) if selected else None


def gdpdu_headers(folder: Path, filename: str) -> list[str]:
    tree = ET.parse(folder / "index.xml")
    for table in tree.iter():
        if table.tag.split("}")[-1] != "Table":
            continue
        url = next(
            (child.text for child in table if child.tag.split("}")[-1] == "URL"), None
        )
        if url != filename:
            continue
        return [
            child.text or ""
            for column in table.iter()
            if column.tag.split("}")[-1] == "VariableColumn"
            for child in column
            if child.tag.split("}")[-1] == "Name"
        ]
    raise ValueError(f"No GDPdU schema for {filename}")


def read_semicolon(path: Path, root: Path, headers: list[str] | None = None) -> list[SourceRow]:
    text = decode_text(path)
    lines = text.splitlines()
    parsed = list(csv.reader(lines, delimiter=";", quotechar='"'))
    if not parsed:
        return []
    fieldnames = headers or [value.strip() for value in parsed[0]]
    start = 0 if headers else 1
    rows: list[SourceRow] = []
    for index, values in enumerate(parsed[start:], start=start + 1):
        padded = values + [""] * max(0, len(fieldnames) - len(values))
        rows.append(
            SourceRow(path, root, index, dict(zip(fieldnames, padded, strict=False)), lines[index - 1])
        )
    return rows


def read_xlsx_table(path: Path, root: Path, required_header: str) -> list[SourceRow]:
    workbook = load_workbook(path, read_only=True, data_only=False)
    rows: list[SourceRow] = []
    for sheet in workbook.worksheets:
        header_index = None
        headers: list[str] = []
        for row in sheet.iter_rows():
            values = [str(cell.value or "").strip() for cell in row]
            if required_header in values:
                header_index = row[0].row
                headers = values
                break
        if header_index is None:
            continue
        for row in sheet.iter_rows(min_row=header_index + 1):
            values = [str(cell.value or "").strip() for cell in row]
            if not any(values):
                continue
            data = dict(zip(headers, values, strict=False))
            cells = {header: cell.coordinate for header, cell in zip(headers, row, strict=False)}
            rows.append(
                SourceRow(
                    path,
                    root,
                    row[0].row,
                    data,
                    " | ".join(values),
                    sheet.title,
                    cells,
                )
            )
    return rows


def read_docx_passages(path: Path, root: Path) -> list[EvidenceRef]:
    document = Document(path)
    refs: list[EvidenceRef] = []
    for index, paragraph in enumerate(document.paragraphs, start=1):
        text = paragraph.text.strip()
        if not text:
            continue
        refs.append(
            EvidenceRef(
                document=relative_name(path, root),
                locator_type="passage",
                passage=f"paragraph:{index}",
                excerpt=text,
                sha256=file_sha256(str(path)),
            )
        )
    return refs


def locate_dossier_root(path: Path) -> Path:
    candidate = path.resolve()
    if (candidate / "Sachkonten" / "index.xml").exists():
        return candidate
    matches = list(candidate.rglob("Sachkonten/index.xml"))
    if len(matches) != 1:
        raise ValueError(f"Expected one GDPdU dossier below {path}, found {len(matches)}")
    return matches[0].parent.parent


def extract_payment_threshold(passages: list[EvidenceRef]) -> tuple[Decimal, EvidenceRef] | None:
    for ref in passages:
        normalized = normalize_text(ref.excerpt)
        if "zahlungsfreig" not in normalized and "vier-augen" not in normalized:
            continue
        match = re.search(r"(?:ab|uber)\s+([0-9][0-9.\s]*)\s*eur", normalized)
        if match:
            control_number = match.group(1).replace(" ", "").replace(".", "")
            return parse_decimal(control_number), ref
    return None
