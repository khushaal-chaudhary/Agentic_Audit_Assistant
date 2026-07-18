"use client";

import { useEffect, useMemo, useState } from "react";

import { AgentBar } from "@/components/agent-bar";
import { AppSidebar } from "@/components/app-sidebar";
import { EvidencePanel } from "@/components/evidence-panel";
import { FindingList } from "@/components/finding-list";
import { QuestionPanel } from "@/components/question-panel";
import { WorkspaceView } from "@/components/workspace-views";
import type {
  DocumentSummary,
  IntegrationStatus,
  JobStatus,
  Report,
  ReviewDisposition,
  ReviewStatus,
  RuleDefinition,
  WorkspaceView as WorkspaceViewName,
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const LAST_JOB_KEY = "auditgraph:lastJobId";
const sleep = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function apiError(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? "Request failed with status " + response.status;
  } catch {
    return "Request failed with status " + response.status;
  }
}

const viewMetadata: Record<WorkspaceViewName, { title: string; subtitle: string }> = {
  overview: { title: "Engagement overview", subtitle: "Evidence coverage and published exceptions" },
  dossier: { title: "Engagement setup", subtitle: "Local ingestion, processing, and connections" },
  documents: { title: "Source documents", subtitle: "Immutable local files and evidence usage" },
  findings: { title: "Journal Entry Testing · Evidence Review", subtitle: "Procedure results requiring auditor judgement" },
  rules: { title: "Deterministic rules", subtitle: "Implemented logic, safeguards, and coverage backlog" },
  analysis: { title: "Data analysis", subtitle: "Procedure execution and evidence density" },
  review: { title: "Report review", subtitle: "Exceptions awaiting auditor disposition" },
};

export default function Home() {
  const [activeView, setActiveView] = useState<WorkspaceViewName>("overview");
  const [report, setReport] = useState<Report | null>(null);
  const [selectedId, setSelectedId] = useState<string>();
  const [integrations, setIntegrations] = useState<IntegrationStatus | null>(null);
  const [rules, setRules] = useState<RuleDefinition[]>([]);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [reviews, setReviews] = useState<ReviewDisposition[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [jobId, setJobId] = useState<string>();
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [findingQuery, setFindingQuery] = useState("");
  const [reviewSavingId, setReviewSavingId] = useState<string>();
  const [error, setError] = useState<string>();

  const selected = useMemo(
    () => report?.findings.find((finding) => finding.id === selectedId) ?? report?.findings[0],
    [report, selectedId],
  );
  const filteredFindings = useMemo(() => {
    const query = findingQuery.trim().toLocaleLowerCase();
    if (!query) return report?.findings ?? [];
    return (report?.findings ?? []).filter((finding) =>
      [finding.title, finding.summary, finding.rule_id, ...finding.affected_entities]
        .join(" ")
        .toLocaleLowerCase()
        .includes(query),
    );
  }, [findingQuery, report]);

  useEffect(() => {
    Promise.all([
      fetch(API_URL + "/api/integrations/status").then((response) => response.json()),
      fetch(API_URL + "/api/rules").then((response) => response.json()),
    ])
      .then(([integrationData, ruleData]: [IntegrationStatus, RuleDefinition[]]) => {
        setIntegrations(integrationData);
        setRules(ruleData);
      })
      .catch(() => {
        setIntegrations(null);
        setRules([]);
      });
  }, []);

  useEffect(() => {
    async function restoreSavedDossier() {
      const savedJobId = window.localStorage.getItem(LAST_JOB_KEY);
      if (!savedJobId) return;
      try {
        const statusResponse = await fetch(
          API_URL + "/api/dossiers/" + savedJobId + "/status",
        );
        if (!statusResponse.ok) throw new Error("Saved dossier is unavailable");
        const current = (await statusResponse.json()) as JobStatus;
        setJobId(current.id);
        setJobStatus(current);
        if (!current.report_ready) return;
        const [reportResponse, documentsResponse, reviewsResponse] = await Promise.all([
          fetch(API_URL + "/api/dossiers/" + current.id + "/report"),
          fetch(API_URL + "/api/dossiers/" + current.id + "/documents"),
          fetch(API_URL + "/api/dossiers/" + current.id + "/reviews"),
        ]);
        if (!reportResponse.ok || !documentsResponse.ok || !reviewsResponse.ok) {
          throw new Error("Saved dossier data is unavailable");
        }
        const data = (await reportResponse.json()) as Report;
        setDocuments((await documentsResponse.json()) as DocumentSummary[]);
        setReviews((await reviewsResponse.json()) as ReviewDisposition[]);
        setReport(data);
        setSelectedId(data.findings[0]?.id);
      } catch {
        window.localStorage.removeItem(LAST_JOB_KEY);
      }
    }

    void restoreSavedDossier();
  }, []);

  async function loadDocuments(currentJobId: string) {
    const response = await fetch(API_URL + "/api/dossiers/" + currentJobId + "/documents");
    if (!response.ok) throw new Error(await apiError(response));
    setDocuments((await response.json()) as DocumentSummary[]);
  }

  async function loadReviews(currentJobId: string) {
    const response = await fetch(API_URL + "/api/dossiers/" + currentJobId + "/reviews");
    if (!response.ok) throw new Error(await apiError(response));
    setReviews((await response.json()) as ReviewDisposition[]);
  }

  async function waitForReport(initial: JobStatus) {
    window.localStorage.setItem(LAST_JOB_KEY, initial.id);
    setJobId(initial.id);
    setJobStatus(initial);
    for (let attempt = 0; attempt < 180; attempt += 1) {
      const statusResponse = await fetch(
        API_URL + "/api/dossiers/" + initial.id + "/status",
      );
      if (!statusResponse.ok) throw new Error(await apiError(statusResponse));
      const current = (await statusResponse.json()) as JobStatus;
      setJobStatus(current);
      if (current.stage === "failed") throw new Error(current.error ?? current.message);
      if (current.report_ready) {
        const reportResponse = await fetch(
          API_URL + "/api/dossiers/" + initial.id + "/report",
        );
        if (!reportResponse.ok) throw new Error(await apiError(reportResponse));
        const data = (await reportResponse.json()) as Report;
        setReport(data);
        setSelectedId(data.findings[0]?.id);
        await Promise.all([loadDocuments(initial.id), loadReviews(initial.id)]);
        setActiveView(data.findings.length ? "findings" : "overview");
        return;
      }
      await sleep(500);
    }
    throw new Error("Dossier processing did not finish within the local demo timeout.");
  }

  async function runDossier(kind: "sample" | "final" | "upload") {
    setLoading(true);
    setError(undefined);
    setReport(null);
    setDocuments([]);
    setReviews([]);
    try {
      let response: Response;
      if (kind === "upload") {
        if (!files.length) throw new Error("Add at least one source file before running an upload.");
        const form = new FormData();
        files.forEach((file) => form.append("files", file));
        response = await fetch(API_URL + "/api/dossiers", { method: "POST", body: form });
      } else {
        response = await fetch(API_URL + "/api/dossiers/" + kind, { method: "POST" });
      }
      if (!response.ok) throw new Error(await apiError(response));
      await waitForReport((await response.json()) as JobStatus);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The audit could not be started.");
    } finally {
      setLoading(false);
    }
  }

  function runDefault() {
    void runDossier(files.length ? "upload" : "final");
  }

  async function syncCognee() {
    if (!jobId) return;
    setSyncing(true);
    setError(undefined);
    try {
      const response = await fetch(
        API_URL + "/api/dossiers/" + jobId + "/cognee-sync",
        { method: "POST" },
      );
      if (!response.ok) throw new Error(await apiError(response));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Cognee sync failed.");
    } finally {
      setSyncing(false);
    }
  }

  function openFinding(findingId: string) {
    setSelectedId(findingId);
    setActiveView("findings");
  }

  async function updateReview(
    findingId: string,
    status: ReviewStatus,
    note: string,
  ) {
    if (!jobId) return;
    setReviewSavingId(findingId);
    setError(undefined);
    try {
      const response = await fetch(
        API_URL + "/api/dossiers/" + jobId + "/reviews/" + findingId,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status, note, reviewer: "Local auditor" }),
        },
      );
      if (!response.ok) throw new Error(await apiError(response));
      const saved = (await response.json()) as ReviewDisposition;
      setReviews((current) => [
        ...current.filter((item) => item.finding_id !== findingId),
        saved,
      ]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Review disposition could not be saved.");
    } finally {
      setReviewSavingId(undefined);
    }
  }

  const notTestable = report?.procedures.filter((item) => item.status === "not_testable") ?? [];
  const noException =
    report?.procedures.filter(
      (procedure) =>
        procedure.status === "completed" &&
        !report.findings.some((finding) => finding.rule_id === procedure.rule_id),
    ).length ?? 0;
  const metadata = viewMetadata[activeView];
  const showIngestion = activeView === "overview" || activeView === "dossier";

  return (
    <main className="flex h-screen overflow-hidden bg-[var(--canvas)] text-[var(--ink)]">
      <AppSidebar
        integrations={integrations}
        dossierName={report?.dossier_name}
        activeView={activeView}
        onSelect={setActiveView}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex min-h-[60px] shrink-0 items-center justify-between border-b border-[var(--line)] bg-white px-4 py-2 md:h-[60px] md:px-[22px] md:py-0">
          <div className="hidden min-w-0 md:block">
            <p className="truncate text-sm font-semibold">{metadata.title}</p>
            <p className="mt-0.5 truncate text-xs text-[var(--muted)]">
              {report
                ? report.files_scanned + " documents · " + report.tests_run + " procedures · " + metadata.subtitle
                : metadata.subtitle}
            </p>
          </div>
          <div className="flex min-w-0 flex-1 items-center gap-2 md:flex-none">
            <select
              aria-label="Workspace view"
              className="min-w-0 flex-1 rounded-lg border border-[var(--line)] bg-white px-2 py-2 text-xs md:hidden"
              onChange={(event) => setActiveView(event.target.value as WorkspaceViewName)}
              value={activeView}
            >
              {Object.entries(viewMetadata).map(([view, item]) => (
                <option key={view} value={view}>{item.title}</option>
              ))}
            </select>
            <button
              className="shrink-0 rounded-lg border border-[var(--line-strong)] bg-white px-3 py-2 text-xs font-semibold hover:bg-[var(--soft)]"
              disabled={loading}
              onClick={runDefault}
            >
              {loading ? "Running…" : "Run agent"}
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="space-y-4 p-4 md:px-[22px] md:pb-[18px] md:pt-3">
            {showIngestion && (
              <AgentBar
                loading={loading}
                syncing={syncing}
                canSync={Boolean(report && jobId && integrations?.cognee.configured)}
                fileCount={files.length}
                jobStatus={jobStatus}
                onFiles={setFiles}
                onRunSample={() => void runDossier("sample")}
                onRunFinal={() => void runDossier("final")}
                onRunUpload={() => void runDossier("upload")}
                onSync={syncCognee}
              />
            )}
            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-800">
                {error}
              </div>
            )}
            {notTestable.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
                {notTestable.map((item) => item.rule_id + ": " + item.reason).join(" · ")}
              </div>
            )}

            {activeView === "findings" ? (
              <>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2 rounded-lg border border-[var(--line)] bg-white p-1.5">
                    <span className="result-chip passed">✓ {noException}</span>
                    <span className="result-chip failed">× {report?.findings.length ?? 0}</span>
                    <span className="result-chip review">— {notTestable.length}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      className="w-[240px] rounded-lg border border-[var(--line)] bg-white px-3 py-2 text-xs outline-none focus:border-[var(--accent)]"
                      onChange={(event) => setFindingQuery(event.target.value)}
                      placeholder="Search findings…"
                      value={findingQuery}
                    />
                    <div className="flex rounded-lg border border-[var(--line)] bg-[#f2f1ec] p-1">
                      <button
                        className={"rounded-md px-3 py-1.5 text-xs " + (!focusMode ? "bg-white font-semibold shadow-sm" : "text-[var(--muted)]")}
                        onClick={() => setFocusMode(false)}
                      >
                        Table
                      </button>
                      <button
                        className={"rounded-md px-3 py-1.5 text-xs " + (focusMode ? "bg-white font-semibold shadow-sm" : "text-[var(--muted)]")}
                        onClick={() => setFocusMode(true)}
                      >
                        Focus
                      </button>
                    </div>
                  </div>
                </div>
                <section
                  className={
                    "grid min-h-[620px] overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-sm " +
                    (focusMode ? "grid-cols-1" : "lg:grid-cols-[minmax(420px,0.92fr)_minmax(500px,1.08fr)]")
                  }
                >
                  {!focusMode && (
                    <FindingList
                      findings={filteredFindings}
                      selectedId={selected?.id}
                      onSelect={setSelectedId}
                    />
                  )}
                  <EvidencePanel finding={selected} apiUrl={API_URL} jobId={jobId} />
                </section>
                <QuestionPanel apiUrl={API_URL} jobId={report ? jobId : undefined} />
              </>
            ) : (
              <WorkspaceView
                view={activeView}
                report={report}
                jobStatus={jobStatus}
                integrations={integrations}
                documents={documents}
                rules={rules}
                reviews={reviews}
                reviewSavingId={reviewSavingId}
                apiUrl={API_URL}
                jobId={jobId}
                onNavigate={setActiveView}
                onOpenFinding={openFinding}
                onReviewUpdate={updateReview}
              />
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
