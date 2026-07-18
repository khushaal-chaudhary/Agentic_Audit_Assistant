export type Evidence = {
  document: string;
  locator_type: string;
  row?: number;
  columns?: string[];
  sheet?: string;
  cell_range?: string;
  page?: number;
  passage?: string;
  query?: string;
  excerpt: string;
  sha256: string;
};

export type Finding = {
  id: string;
  rule_id: string;
  category: "fraud" | "misstatement" | "control";
  severity: "high" | "medium" | "low";
  confidence: string;
  title: string;
  summary: string;
  amount?: string;
  currency?: string;
  affected_entities: string[];
  evidence: Evidence[];
  counterevidence_considered: string[];
  next_step: string;
};

export type Procedure = {
  rule_id: string;
  status: "completed" | "not_testable";
  reason?: string;
};

export type Report = {
  dossier_name: string;
  files_scanned: number;
  tests_run: number;
  findings: Finding[];
  procedures: Procedure[];
  suppressed_leads: number;
};

export type JobStatus = {
  id: string;
  dossier_name: string;
  stage: string;
  progress: number;
  message: string;
  report_ready: boolean;
  error?: string;
};

export type GroundedClaim = {
  statement: string;
  finding_ids: string[];
  evidence: Evidence[];
};

export type GroundedAnswer = {
  status: "answered" | "not_testable";
  claims: GroundedClaim[];
  provider: "openai" | "deterministic";
  note: string;
};

export type IntegrationStatus = {
  cognee: { configured: boolean };
  openai: { configured: boolean };
};

export type WorkspaceView =
  | "overview"
  | "dossier"
  | "documents"
  | "findings"
  | "rules"
  | "analysis"
  | "review";

export type DocumentSummary = {
  path: string;
  name: string;
  extension: string;
  size_bytes: number;
  sha256: string;
  evidence_locations: number;
};

export type RuleDefinition = {
  rule_id: string;
  name: string;
  status: "implemented" | "planned";
  category: "fraud" | "misstatement" | "control" | "reconciliation";
  severity?: "high" | "medium" | "low";
  objective: string;
  required_inputs: string[];
  publication_conditions: string[];
  false_positive_guards: string[];
  evidence_requirements: string[];
};

export function money(value?: string, currency = "EUR") {
  if (!value) return "—";
  const negative = value.startsWith("-");
  const unsigned = negative ? value.slice(1) : value;
  const [whole = "0", fraction = ""] = unsigned.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const decimals = fraction.padEnd(2, "0").slice(0, 2);
  const amount = (negative ? "−" : "") + grouped + "," + decimals;
  return currency === "EUR" ? amount + " €" : amount + " " + currency;
}

export function evidenceUrl(apiUrl: string, jobId: string, evidence: Evidence) {
  const encoded = evidence.document.split("/").map(encodeURIComponent).join("/");
  const page = evidence.page ? "#page=" + evidence.page : "";
  return apiUrl + "/api/dossiers/" + jobId + "/documents/" + encoded + page;
}

export function documentUrl(apiUrl: string, jobId: string, path: string) {
  const encoded = path.split("/").map(encodeURIComponent).join("/");
  return apiUrl + "/api/dossiers/" + jobId + "/documents/" + encoded;
}

export function evidenceLocator(evidence: Evidence) {
  if (evidence.sheet) return evidence.sheet + " · " + (evidence.cell_range ?? "cell");
  if (evidence.row) return "row " + evidence.row;
  if (evidence.page) return "page " + evidence.page;
  return evidence.passage ?? evidence.query ?? evidence.locator_type;
}
