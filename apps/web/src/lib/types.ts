export type Evidence = {
  document: string;
  locator_type: string;
  row?: number;
  sheet?: string;
  cell_range?: string;
  passage?: string;
  excerpt: string;
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

export type Report = {
  dossier_name: string;
  files_scanned: number;
  tests_run: number;
  findings: Finding[];
  suppressed_leads: number;
};

export type IntegrationStatus = {
  cognee: { configured: boolean };
  openai: { configured: boolean };
};

export function money(value?: string, currency = "EUR") {
  if (!value) return "—";
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(Number(value));
}

