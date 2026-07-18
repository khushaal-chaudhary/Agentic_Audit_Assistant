from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .models import DossierReport, EvidenceRef


class DossierNode(BaseModel):
    type: Literal["dossier"] = "dossier"
    id: str
    name: str


class ProcedureNode(BaseModel):
    type: Literal["procedure"] = "procedure"
    id: str
    rule_id: str
    status: Literal["completed", "not_testable"]
    reason: str | None = None


class DocumentNode(BaseModel):
    type: Literal["document"] = "document"
    id: str
    path: str
    sha256: str


class LocatorNode(BaseModel):
    type: Literal["locator"] = "locator"
    id: str
    document: str
    locator_type: str
    row: int | None = None
    sheet: str | None = None
    cell_range: str | None = None
    page: int | None = None
    passage: str | None = None
    query: str | None = None
    excerpt: str
    sha256: str


class FindingNode(BaseModel):
    type: Literal["finding"] = "finding"
    id: str
    rule_id: str
    category: str
    severity: str
    confidence: str
    title: str
    summary: str


class EntityNode(BaseModel):
    type: Literal["entity"] = "entity"
    id: str
    label: str


class CalculationNode(BaseModel):
    type: Literal["calculation"] = "calculation"
    id: str
    value: str
    currency: str | None
    method: Literal["deterministic_rule_aggregation"] = "deterministic_rule_aggregation"
    operation: Literal["sum"] = "sum"
    term_count: int = Field(ge=1)


GraphNode = Annotated[
    DossierNode
    | ProcedureNode
    | DocumentNode
    | LocatorNode
    | FindingNode
    | EntityNode
    | CalculationNode,
    Field(discriminator="type"),
]


class GraphEdge(BaseModel):
    source: str
    relation: Literal[
        "CONTAINS",
        "PRODUCED",
        "SUPPORTED_BY",
        "LOCATED_IN",
        "AFFECTS",
        "HAS_CALCULATION",
        "DERIVED_FROM",
    ]
    target: str


class EvidenceGraph(BaseModel):
    schema_version: Literal["1.1"] = "1.1"
    nodes: list[GraphNode]
    edges: list[GraphEdge]


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _locator_id(reference: EvidenceRef) -> str:
    return _stable_id("locator", reference.model_dump_json(exclude_none=True))


def build_evidence_graph(report: DossierReport) -> EvidenceGraph:
    dossier_id = _stable_id("dossier", report.dossier_name)
    nodes: list[GraphNode] = [DossierNode(id=dossier_id, name=report.dossier_name)]
    edges: list[GraphEdge] = []
    known_nodes = {dossier_id}

    for procedure in report.procedures:
        procedure_id = f"procedure:{procedure.rule_id}"
        nodes.append(
            ProcedureNode(
                id=procedure_id,
                rule_id=procedure.rule_id,
                status=procedure.status,
                reason=procedure.reason,
            )
        )
        known_nodes.add(procedure_id)
        edges.append(GraphEdge(source=dossier_id, relation="CONTAINS", target=procedure_id))

    for finding in report.findings:
        finding_id = f"finding:{finding.id}"
        nodes.append(
            FindingNode(
                id=finding_id,
                rule_id=finding.rule_id,
                category=finding.category,
                severity=finding.severity,
                confidence=format(finding.confidence, "f"),
                title=finding.title,
                summary=finding.summary,
            )
        )
        known_nodes.add(finding_id)
        procedure_id = f"procedure:{finding.rule_id}"
        if procedure_id in known_nodes:
            edges.append(GraphEdge(source=procedure_id, relation="PRODUCED", target=finding_id))

        for reference in finding.evidence:
            document_id = _stable_id("document", f"{reference.document}|{reference.sha256}")
            if document_id not in known_nodes:
                nodes.append(
                    DocumentNode(
                        id=document_id,
                        path=reference.document,
                        sha256=reference.sha256,
                    )
                )
                known_nodes.add(document_id)
            locator_id = _locator_id(reference)
            if locator_id not in known_nodes:
                nodes.append(
                    LocatorNode(
                        id=locator_id,
                        document=reference.document,
                        locator_type=reference.locator_type,
                        row=reference.row,
                        sheet=reference.sheet,
                        cell_range=reference.cell_range,
                        page=reference.page,
                        passage=reference.passage,
                        query=reference.query,
                        excerpt=reference.excerpt,
                        sha256=reference.sha256,
                    )
                )
                known_nodes.add(locator_id)
                edges.append(
                    GraphEdge(source=locator_id, relation="LOCATED_IN", target=document_id)
                )
            edges.append(
                GraphEdge(source=finding_id, relation="SUPPORTED_BY", target=locator_id)
            )

        for label in finding.affected_entities:
            entity_id = _stable_id("entity", label)
            if entity_id not in known_nodes:
                nodes.append(EntityNode(id=entity_id, label=label))
                known_nodes.add(entity_id)
            edges.append(GraphEdge(source=finding_id, relation="AFFECTS", target=entity_id))

        if finding.amount is not None:
            if finding.calculation is None:
                raise ValueError(f"Finding {finding.id} has no exact calculation trace")
            calculation_id = f"calculation:{finding.id}"
            term_locator_ids = [
                _locator_id(term.evidence)
                for term in finding.calculation.terms
            ]
            nodes.append(
                CalculationNode(
                    id=calculation_id,
                    value=format(finding.amount, "f"),
                    currency=finding.currency,
                    operation=finding.calculation.operation,
                    term_count=len(term_locator_ids),
                )
            )
            edges.append(
                GraphEdge(source=finding_id, relation="HAS_CALCULATION", target=calculation_id)
            )
            edges.extend(
                GraphEdge(source=calculation_id, relation="DERIVED_FROM", target=locator_id)
                for locator_id in term_locator_ids
            )

    graph = EvidenceGraph(nodes=nodes, edges=edges)
    validate_evidence_graph(graph)
    return graph


def validate_evidence_graph(graph: EvidenceGraph) -> None:
    supported = {edge.source for edge in graph.edges if edge.relation == "SUPPORTED_BY"}
    calculated = {edge.target for edge in graph.edges if edge.relation == "HAS_CALCULATION"}
    derived = {edge.source for edge in graph.edges if edge.relation == "DERIVED_FROM"}
    derived_targets: dict[str, set[str]] = {}
    for edge in graph.edges:
        if edge.relation == "DERIVED_FROM":
            derived_targets.setdefault(edge.source, set()).add(edge.target)
    for node in graph.nodes:
        if node.type == "finding" and node.id not in supported:
            raise ValueError(f"Finding graph node has no source locator: {node.id}")
        if node.type == "calculation" and node.id not in derived:
            raise ValueError(f"Calculation graph node has no source locator: {node.id}")
        if (
            node.type == "calculation"
            and len(derived_targets.get(node.id, set())) != node.term_count
        ):
            raise ValueError(
                f"Calculation graph node has incomplete term lineage: {node.id}"
            )
    orphaned_calculations = {
        node.id for node in graph.nodes if node.type == "calculation"
    } - calculated
    if orphaned_calculations:
        raise ValueError(f"Unlinked calculations: {sorted(orphaned_calculations)}")


def graph_json(report: DossierReport) -> bytes:
    graph = build_evidence_graph(report)
    return json.dumps(graph.model_dump(mode="json"), ensure_ascii=False, indent=2).encode("utf-8")
