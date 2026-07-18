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
        journal_approvals: list[SourceRow] | None = None,
        jet_planning: list[EvidenceRef] | None = None,
    ) -> AuditEngine:
        engine = AuditEngine.__new__(AuditEngine)
        engine.root = self.root
        engine.gl_path = self.source_path("Sachkonten/Sachkontobuchungen.txt")
        engine.manual_gl_path = engine.gl_path
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
        engine.jet_planning_path = self.source_path(
            "Begleitdokumente/JET_Planung.docx"
        )
        engine.approval_path = self.root / "__missing_role_journal_approvals"
        engine.export_manifest_path = self.root / "__missing_role_export_manifest"
        engine.it_confirmation_path = (
            self.root / "__missing_role_it_completeness_confirmation"
        )
        engine._path_issues = {}
        engine.discovery = None
        engine.gl = gl or []
        engine.vendor_postings = vendor_postings or []
        engine.receipts = receipts or []
        engine.changes = changes or []
        engine.permissions = permissions or []
        engine.assets = assets or []
        engine.asset_postings = asset_postings or []
        engine.future_invoices = future_invoices or []
        engine.planning = planning or []
        engine.journal_approvals = journal_approvals or []
        engine.jet_planning = jet_planning if jet_planning is not None else engine.planning
        engine.gl_by_capture = {}
        engine.gl_row_count = len(engine.gl)
        engine._build_indexes()
        return engine
