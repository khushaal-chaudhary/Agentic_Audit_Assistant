"use client";

import { useState } from "react";

import type {
  DocumentSummary,
  Finding,
  IntegrationStatus,
  JobStatus,
  Report,
  ReviewDisposition,
  ReviewStatus,
  RuleDefinition,
  WorkspaceView,
} from "@/lib/types";
import { documentUrl } from "@/lib/types";

type Props = {
  view: Exclude<WorkspaceView, "findings">;
  report: Report | null;
  jobStatus: JobStatus | null;
  integrations: IntegrationStatus | null;
  documents: DocumentSummary[];
  rules: RuleDefinition[];
  reviews: ReviewDisposition[];
  reviewSavingId?: string;
  apiUrl: string;
  jobId?: string;
  onNavigate: (view: WorkspaceView) => void;
  onOpenFinding: (findingId: string) => void;
  onReviewUpdate: (
    findingId: string,
    status: ReviewStatus,
    note: string,
  ) => Promise<void>;
};

function EmptyDossier({ onNavigate }: { onNavigate: (view: WorkspaceView) => void }) {
  return (
    <div className="grid min-h-[460px] place-items-center rounded-2xl border border-[var(--line)] bg-white p-10 text-center shadow-sm">
      <div className="max-w-md">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-[var(--mint)] text-lg text-[var(--green)]">
          A
        </div>
        <h2 className="mt-4 text-xl font-semibold">Load an evidence dossier</h2>
        <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
          Run the preloaded final dossier or upload a ZIP to populate this workspace with sourced
          procedures, documents, findings, and review items.
        </p>
        <button className="primary-button mt-5" onClick={() => onNavigate("dossier")}>
          Open engagement
        </button>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  detail: string;
  tone?: "neutral" | "danger" | "success";
}) {
  const valueClass =
    tone === "danger"
      ? "text-[var(--danger)]"
      : tone === "success"
        ? "text-[var(--accent)]"
        : "text-[var(--ink)]";
  return (
    <div className="rounded-xl border border-[var(--line)] bg-white p-5">
      <p className="eyebrow">{label}</p>
      <p className={"mt-3 text-3xl font-semibold tracking-[-0.03em] " + valueClass}>{value}</p>
      <p className="mt-2 text-xs text-[var(--muted)]">{detail}</p>
    </div>
  );
}

function Overview({
  report,
  rules,
  onNavigate,
}: Pick<Props, "report" | "rules" | "onNavigate">) {
  if (!report) return <EmptyDossier onNavigate={onNavigate} />;
  const notTestable = report.procedures.filter((item) => item.status === "not_testable");
  const implemented = rules.filter((rule) => rule.status === "implemented");
  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-[var(--line)] bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="eyebrow">Engagement overview</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.02em]">
              {report.dossier_name}
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--muted)]">
              Deterministic procedures ran against the local evidence set. Published exceptions
              remain linked to exact source locations; suppressed leads are retained only as counts.
            </p>
          </div>
          <button className="primary-button" onClick={() => onNavigate("findings")}>
            Review findings
          </button>
        </div>
      </section>
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Documents" value={report.files_scanned} detail="Local source files scanned" />
        <Metric
          label="Procedures"
          value={report.tests_run}
          detail={implemented.length + " deterministic rules implemented"}
          tone="success"
        />
        <Metric
          label="Findings"
          value={report.findings.length}
          detail="Require auditor judgement"
          tone={report.findings.length ? "danger" : "success"}
        />
        <Metric
          label="Not testable"
          value={notTestable.length}
          detail="Missing required evidence"
        />
      </section>
      <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-2xl border border-[var(--line)] bg-white p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Procedure coverage</h3>
            <button className="text-xs font-semibold text-[var(--accent)]" onClick={() => onNavigate("rules")}>
              View rulebook
            </button>
          </div>
          <div className="mt-4 space-y-2">
            {report.procedures.map((procedure) => {
              const finding = report.findings.find((item) => item.rule_id === procedure.rule_id);
              const label =
                procedure.status === "not_testable"
                  ? "Not testable"
                  : finding
                    ? "Finding"
                    : "No exception";
              return (
                <div
                  className="flex items-center justify-between rounded-lg border border-[var(--line)] px-3 py-3"
                  key={procedure.rule_id}
                >
                  <span className="font-mono text-xs">{procedure.rule_id}</span>
                  <span
                    className={
                      "result-chip " +
                      (label === "Finding"
                        ? "failed"
                        : label === "No exception"
                          ? "passed"
                          : "review")
                    }
                  >
                    {label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
        <div className="rounded-2xl border border-[var(--line)] bg-[var(--green)] p-5 text-white">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-white/50">
            Precision controls
          </p>
          <p className="mt-3 text-lg font-semibold">{report.suppressed_leads} leads suppressed</p>
          <p className="mt-2 text-sm leading-6 text-white/65">
            Candidates that failed corroboration or counterevidence checks were not published as
            findings.
          </p>
        </div>
      </section>
    </div>
  );
}

function Engagement({
  report,
  jobStatus,
  integrations,
  onNavigate,
}: Pick<Props, "report" | "jobStatus" | "integrations" | "onNavigate">) {
  return (
    <div className="space-y-4">
      {!report && <EmptyDossier onNavigate={onNavigate} />}
      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-[var(--line)] bg-white p-5">
          <p className="eyebrow">Processing state</p>
          <h2 className="mt-3 text-xl font-semibold">{jobStatus?.message ?? "No active job"}</h2>
          <div className="mt-5 h-2 overflow-hidden rounded-full bg-[var(--soft)]">
            <div
              className="h-full rounded-full bg-[var(--mint-strong)]"
              style={{ width: String(jobStatus?.progress ?? 0) + "%" }}
            />
          </div>
          <div className="mt-3 flex justify-between text-xs text-[var(--muted)]">
            <span>{jobStatus?.stage ?? "waiting"}</span>
            <span>{jobStatus?.progress ?? 0}%</span>
          </div>
        </div>
        <div className="rounded-2xl border border-[var(--line)] bg-white p-5">
          <p className="eyebrow">Service connections</p>
          <div className="mt-4 space-y-3">
            {[
              ["Local deterministic engine", true],
              ["OpenAI grounded explanations", Boolean(integrations?.openai.configured)],
              ["Cognee evidence projection", Boolean(integrations?.cognee.configured)],
            ].map(([label, connected]) => (
              <div className="flex items-center justify-between" key={String(label)}>
                <span className="text-sm">{label}</span>
                <span className={"result-chip " + (connected ? "passed" : "review")}>
                  {connected ? "Ready" : "Optional"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>
      {report && (
        <section className="rounded-2xl border border-[var(--line)] bg-white p-5">
          <p className="eyebrow">Dossier facts</p>
          <dl className="mt-4 grid gap-4 sm:grid-cols-3">
            <div><dt className="text-xs text-[var(--muted)]">Name</dt><dd className="mt-1 text-sm font-semibold">{report.dossier_name}</dd></div>
            <div><dt className="text-xs text-[var(--muted)]">Files scanned</dt><dd className="mt-1 text-sm font-semibold">{report.files_scanned}</dd></div>
            <div><dt className="text-xs text-[var(--muted)]">Tests completed</dt><dd className="mt-1 text-sm font-semibold">{report.tests_run}</dd></div>
          </dl>
        </section>
      )}
    </div>
  );
}

function formatBytes(size: number) {
  if (size < 1024) return size + " B";
  if (size < 1024 * 1024) return Math.round(size / 1024) + " KB";
  return (size / (1024 * 1024)).toFixed(1) + " MB";
}

function Documents({
  report,
  documents,
  apiUrl,
  jobId,
  onNavigate,
}: Pick<Props, "report" | "documents" | "apiUrl" | "jobId" | "onNavigate">) {
  if (!report || !jobId) return <EmptyDossier onNavigate={onNavigate} />;
  const recognized = documents.filter(
    (document) => document.ingestion_status === "recognized",
  ).length;
  const exceptions = documents.filter(
    (document) =>
      document.ingestion_status === "ambiguous"
      || document.ingestion_status === "unsupported"
      || document.extraction_status === "partial",
  ).length;
  const nativePdfPages = documents.reduce(
    (total, document) => total + (document.extraction_status === "not_applicable" ? 0 : document.extracted_pages),
    0,
  );
  return (
    <section className="overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold">Source document inventory</h2>
          <p className="mt-1 text-xs text-[var(--muted)]">
            {documents.length} files retained · {recognized} recognized · {nativePdfPages} PDF pages extracted · {exceptions} need attention
          </p>
        </div>
        <span className="result-chip passed">Evidence bound</span>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_90px_100px_120px] border-b border-[var(--line)] bg-[var(--soft)] px-5 py-2 text-[10px] font-bold uppercase tracking-[0.11em] text-[var(--muted)]">
        <span>Document</span><span>Type</span><span>Size</span><span>Evidence</span>
      </div>
      <div className="max-h-[620px] overflow-y-auto">
        {documents.map((document) => (
          <a
            className="grid grid-cols-[minmax(0,1fr)_90px_100px_120px] items-center border-b border-[var(--line)] px-5 py-3 text-sm hover:bg-[var(--soft)]"
            href={documentUrl(apiUrl, jobId, document.path)}
            key={document.path}
            rel="noreferrer"
            target="_blank"
          >
            <span className="min-w-0">
              <span className="block truncate font-medium">{document.name}</span>
              <span className="mt-1 block truncate font-mono text-[10px] text-[var(--muted)]">
                {document.sha256.slice(0, 16)}…
              </span>
              <span className="mt-1 block truncate text-[10px] text-[var(--muted)]">
                {document.role
                  ? "Role: " + document.role.replaceAll("_", " ")
                  : document.ingestion_reason ?? "Inventory only"}
              </span>
              {document.page_count !== undefined && document.page_count !== null && (
                <span className="mt-1 block truncate text-[10px] text-[var(--muted)]">
                  Native PDF text: {document.extracted_pages}/{document.page_count} pages · {document.passage_count} passages
                </span>
              )}
            </span>
            <span className="uppercase text-[var(--muted)]">{document.extension}</span>
            <span className="text-[var(--muted)]">{formatBytes(document.size_bytes)}</span>
            <span className={document.evidence_locations ? "font-semibold text-[var(--accent)]" : "text-[var(--muted)]"}>
              {document.evidence_locations
                ? document.evidence_locations + " locations"
                : document.passage_count
                  ? document.passage_count + " passages"
                  : "Not cited"}
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}

function Rules({ rules }: Pick<Props, "rules">) {
  const implemented = rules.filter((rule) => rule.status === "implemented");
  const planned = rules.filter((rule) => rule.status === "planned");
  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-[var(--line)] bg-white p-6 shadow-sm">
        <p className="eyebrow">Deterministic rulebook</p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold">What the engine tests</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--muted)]">
              Implemented rules run locally and publish only corroborated, source-linked exceptions.
              Planned rules are visible for coverage planning but never appear as completed tests.
            </p>
          </div>
          <div className="flex gap-2">
            <span className="result-chip passed">{implemented.length} implemented</span>
            <span className="result-chip review">{planned.length} planned</span>
          </div>
        </div>
      </section>
      <section className="space-y-3">
        {implemented.map((rule, index) => (
          <details
            className="group rounded-2xl border border-[var(--line)] bg-white shadow-sm"
            key={rule.rule_id}
            open={index === 0}
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="result-chip passed">Implemented</span>
                  <span className="result-chip review">{rule.category}</span>
                </div>
                <h3 className="mt-2 text-base font-semibold">{rule.name}</h3>
                <p className="mt-1 font-mono text-[10px] text-[var(--muted)]">{rule.rule_id}</p>
              </div>
              <span className="text-xl text-[var(--muted)] group-open:rotate-45">+</span>
            </summary>
            <div className="border-t border-[var(--line)] px-5 py-5">
              <p className="text-sm leading-6 text-[var(--muted)]">{rule.objective}</p>
              <div className="mt-5 grid gap-5 lg:grid-cols-3">
                <RuleList title="Required inputs" items={rule.required_inputs} />
                <RuleList title="Publication conditions" items={rule.publication_conditions} />
                <RuleList title="False-positive guards" items={rule.false_positive_guards} />
              </div>
              <div className="mt-5 rounded-xl bg-[var(--mint)] p-4">
                <RuleList title="Evidence required" items={rule.evidence_requirements} />
              </div>
            </div>
          </details>
        ))}
      </section>
      <section className="rounded-2xl border border-dashed border-[var(--line-strong)] bg-white/60 p-5">
        <h3 className="text-sm font-semibold">Coverage backlog</h3>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {planned.map((rule) => (
            <div className="rounded-xl border border-[var(--line)] bg-white p-4" key={rule.rule_id}>
              <span className="result-chip review">Planned</span>
              <p className="mt-3 text-sm font-semibold">{rule.name}</p>
              <p className="mt-2 text-xs leading-5 text-[var(--muted)]">{rule.objective}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function RuleList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--muted)]">{title}</p>
      <ul className="mt-3 space-y-2">
        {items.map((item) => (
          <li className="flex gap-2 text-xs leading-5 text-[var(--ink)]" key={item}>
            <span className="text-[var(--mint-strong)]">●</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Analysis({
  report,
  rules,
  onNavigate,
}: Pick<Props, "report" | "rules" | "onNavigate">) {
  if (!report) return <EmptyDossier onNavigate={onNavigate} />;
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_0.8fr]">
      <section className="rounded-2xl border border-[var(--line)] bg-white p-5">
        <h2 className="text-sm font-semibold">Procedure execution matrix</h2>
        <div className="mt-4 space-y-3">
          {rules.filter((rule) => rule.status === "implemented").map((rule) => {
            const procedure = report.procedures.find((item) => item.rule_id === rule.rule_id);
            const finding = report.findings.find((item) => item.rule_id === rule.rule_id);
            return (
              <div className="rounded-xl border border-[var(--line)] p-4" key={rule.rule_id}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold">{rule.name}</p>
                    <p className="mt-1 font-mono text-[10px] text-[var(--muted)]">{rule.rule_id}</p>
                  </div>
                  <span className={"result-chip " + (finding ? "failed" : procedure?.status === "completed" ? "passed" : "review")}>
                    {finding ? "Exception" : procedure?.status === "completed" ? "No exception" : "Not testable"}
                  </span>
                </div>
                <p className="mt-3 text-xs leading-5 text-[var(--muted)]">{rule.objective}</p>
              </div>
            );
          })}
        </div>
      </section>
      <section className="space-y-4">
        <div className="rounded-2xl border border-[var(--line)] bg-white p-5">
          <p className="eyebrow">Evidence density</p>
          <p className="mt-3 text-3xl font-semibold">
            {report.findings.reduce((count, finding) => count + finding.evidence.length, 0)}
          </p>
          <p className="mt-2 text-xs text-[var(--muted)]">Source locations attached to findings</p>
        </div>
        <div className="rounded-2xl border border-[var(--line)] bg-white p-5">
          <p className="eyebrow">Published categories</p>
          <div className="mt-4 space-y-2">
            {(["fraud", "misstatement", "control"] as const).map((category) => (
              <div className="flex justify-between text-sm" key={category}>
                <span className="capitalize">{category}</span>
                <span className="font-semibold">{report.findings.filter((item) => item.category === category).length}</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function ReviewRow({
  finding,
  review,
  saving,
  onOpenFinding,
  onReviewUpdate,
}: {
  finding: Finding;
  review?: ReviewDisposition;
  saving: boolean;
  onOpenFinding: Props["onOpenFinding"];
  onReviewUpdate: Props["onReviewUpdate"];
}) {
  const [note, setNote] = useState(review?.note ?? "");
  const status = review?.status ?? "pending";

  const chipClass =
    status === "confirmed"
      ? "failed"
      : status === "dismissed"
        ? "passed"
        : "review";
  const statusLabel =
    status === "confirmed"
      ? "Confirmed exception"
      : status === "dismissed"
        ? "Dismissed"
        : "Needs review";

  return (
    <article className="border-b border-[var(--line)] p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <button
          className="min-w-0 flex-1 text-left"
          onClick={() => onOpenFinding(finding.id)}
        >
          <span className="block text-sm font-medium hover:text-[var(--accent)]">
            {finding.title}
          </span>
          <span className="mt-1 block font-mono text-[10px] text-[var(--muted)]">
            {finding.rule_id}
          </span>
        </button>
        <span className={"result-chip " + chipClass}>{statusLabel}</span>
      </div>
      <label className="mt-4 block">
        <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--muted)]">
          Auditor rationale
        </span>
        <textarea
          aria-label={"Review note for " + finding.title}
          className="mt-2 min-h-20 w-full resize-y rounded-lg border border-[var(--line)] bg-white px-3 py-2 text-xs leading-5 outline-none focus:border-[var(--accent)]"
          onChange={(event) => setNote(event.target.value)}
          placeholder="Record corroboration, follow-up, or the reason this exception is dismissed."
          value={note}
        />
      </label>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          className="rounded-lg bg-[var(--green)] px-3 py-2 text-xs font-semibold text-white disabled:opacity-40"
          disabled={saving}
          onClick={() => onReviewUpdate(finding.id, "confirmed", note)}
        >
          Confirm exception
        </button>
        <button
          className="rounded-lg border border-[var(--line-strong)] bg-white px-3 py-2 text-xs font-semibold disabled:opacity-40"
          disabled={saving || note.trim().length < 5}
          onClick={() => onReviewUpdate(finding.id, "dismissed", note)}
        >
          Dismiss with rationale
        </button>
        {status !== "pending" && (
          <button
            className="px-2 py-2 text-xs font-semibold text-[var(--muted)] disabled:opacity-40"
            disabled={saving}
            onClick={() => onReviewUpdate(finding.id, "pending", note)}
          >
            Reset review
          </button>
        )}
        {saving && <span className="text-xs text-[var(--muted)]">Saving…</span>}
        {review && !saving && (
          <span className="ml-auto text-[10px] text-[var(--muted)]">
            {review.reviewer} · {new Date(review.updated_at).toLocaleString()}
          </span>
        )}
      </div>
    </article>
  );
}

function Review({
  report,
  reviews,
  reviewSavingId,
  onNavigate,
  onOpenFinding,
  onReviewUpdate,
}: Pick<
  Props,
  | "report"
  | "reviews"
  | "reviewSavingId"
  | "onNavigate"
  | "onOpenFinding"
  | "onReviewUpdate"
>) {
  if (!report) return <EmptyDossier onNavigate={onNavigate} />;
  const byFinding = new Map(reviews.map((review) => [review.finding_id, review]));
  const confirmed = reviews.filter((review) => review.status === "confirmed").length;
  const dismissed = reviews.filter((review) => review.status === "dismissed").length;
  return (
    <section className="overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--line)] px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold">Auditor review queue</h2>
          <p className="mt-1 text-xs text-[var(--muted)]">
            Dispositions persist with this local dossier. Dismissals require a rationale.
          </p>
        </div>
        <div className="flex gap-2">
          <span className="result-chip review">
            {report.findings.length - confirmed - dismissed} pending
          </span>
          <span className="result-chip failed">{confirmed} confirmed</span>
          <span className="result-chip passed">{dismissed} dismissed</span>
        </div>
      </div>
      {report.findings.length ? report.findings.map((finding) => {
        const review = byFinding.get(finding.id);
        return (
          <ReviewRow
            finding={finding}
            key={finding.id + ":" + (review?.updated_at ?? "pending")}
            onOpenFinding={onOpenFinding}
            onReviewUpdate={onReviewUpdate}
            review={review}
            saving={reviewSavingId === finding.id}
          />
        );
      }) : (
        <p className="p-8 text-center text-sm text-[var(--muted)]">No findings require review.</p>
      )}
    </section>
  );
}

export function WorkspaceView(props: Props) {
  if (props.view === "overview") return <Overview {...props} />;
  if (props.view === "dossier") return <Engagement {...props} />;
  if (props.view === "documents") return <Documents {...props} />;
  if (props.view === "rules") return <Rules {...props} />;
  if (props.view === "analysis") return <Analysis {...props} />;
  return <Review {...props} />;
}
