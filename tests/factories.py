from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from audit_core.engine import AuditEngine
from audit_core.models import EvidenceRef
from audit_core.parsers import SourceRow


class ScenarioFactory:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._row_number = 1

    def source_path(self, name: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")
        return path

    def row(self, name: str, **data: str) -> SourceRow:
        path = self.source_path(name)
        raw = ";".join(f"{key}={value}" for key, value in data.items())
        with path.open("a", encoding="utf-8") as stream:
            stream.write(raw + "\n")
        row = SourceRow(
            source=path,
            root=self.root,
            row_number=self._row_number,
            data=data,
            raw=raw,
        )
        self._row_number += 1
        return row

    def passage(self, name: str, text: str, paragraph: int = 1) -> EvidenceRef:
        path = self.source_path(name)
        path.write_text(text, encoding="utf-8")
        return EvidenceRef(
            document=path.relative_to(self.root).as_posix(),
            locator_type="passage",
            passage=f"paragraph:{paragraph}",
            excerpt=text,
            sha256=sha256(path.read_bytes()).hexdigest(),
        )

    def engine(
        self,
        *,
        gl: list[SourceRow] | None = None,
        vendor_postings: list[SourceRow] | None = None,
        receipts: list[SourceRow] | None = None,
        changes: list[SourceRow] | None = None,
        permissions: list[SourceRow] | None = None,
        assets: list[SourceRow] | None = None,
        asset_postings: list[SourceRow] | None = None,
        future_invoices: list[SourceRow] | None = None,
        planning: list[EvidenceRef] | None = None,
    ) -> AuditEngine:
        engine = AuditEngine.__new__(AuditEngine)
        engine.root = self.root
        engine.gl_path = self.source_path("Sachkonten/Sachkontobuchungen.txt")
        engine.vendor_path = self.source_path("Kreditoren/Lieferantenbuchungen.txt")
        engine.asset_path = self.source_path("AV/Anlagen.txt")
        engine.asset_posting_path = self.source_path("AV/Anlagenbuchungen.txt")
        engine.receipt_path = self.source_path("Begleitdokumente/Wareneingangsliste.csv")
        engine.change_path = self.source_path("Begleitdokumente/Stammdatenaenderungen.csv")
        engine.permission_path = self.source_path("Begleitdokumente/Berechtigungen.xlsx")
        engine.future_invoice_path = self.source_path(
            "Begleitdokumente/Fakturajournal_Kreditoren.csv"
        )
        engine.planning_path = self.source_path("Begleitdokumente/Pruefungsplanung.docx")
        engine.gl = gl or []
        engine.vendor_postings = vendor_postings or []
        engine.receipts = receipts or []
        engine.changes = changes or []
        engine.permissions = permissions or []
        engine.assets = assets or []
        engine.asset_postings = asset_postings or []
        engine.future_invoices = future_invoices or []
        engine.planning = planning or []
        engine._build_indexes()
        return engine
