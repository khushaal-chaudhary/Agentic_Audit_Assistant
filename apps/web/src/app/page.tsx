"use client";

import { useEffect, useMemo, useState } from "react";

import { AgentBar } from "@/components/agent-bar";
import { AppSidebar } from "@/components/app-sidebar";
import { EvidencePanel } from "@/components/evidence-panel";
import { FindingList } from "@/components/finding-list";
import { QuestionPanel } from "@/components/question-panel";
import type { IntegrationStatus, JobStatus, Report } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const sleep = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));
async function apiError(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export default function Home() {
  const [report, setReport] = useState<Report | null>(null);
  const [selectedId, setSelectedId] = useState<string>();
  const [integrations, setIntegrations] = useState<IntegrationStatus | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [jobId, setJobId] = useState<string>();
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string>();
  const selected = useMemo(
    () => report?.findings.find((finding) => finding.id === selectedId) ?? report?.findings[0],
    [report, selectedId],
  );

  useEffect(() => {
    fetch(`${API_URL}/api/integrations/status`)
      .then((response) => response.json())
      .then((data: IntegrationStatus) => setIntegrations(data))
      .catch(() => setIntegrations(null));
  }, []);

  async function waitForReport(initial: JobStatus) {
    setJobId(initial.id);
    setJobStatus(initial);
    for (let attempt = 0; attempt < 180; attempt += 1) {
      const statusResponse = await fetch(`${API_URL}/api/dossiers/${initial.id}/status`);
      if (!statusResponse.ok) throw new Error(await apiError(statusResponse));
      const current = (await statusResponse.json()) as JobStatus;
      setJobStatus(current);
      if (current.stage === "failed") throw new Error(current.error ?? current.message);
      if (current.report_ready) {
        const reportResponse = await fetch(`${API_URL}/api/dossiers/${initial.id}/report`);
        if (!reportResponse.ok) throw new Error(await apiError(reportResponse));
        const data = (await reportResponse.json()) as Report;
        setReport(data);
        setSelectedId(data.findings[0]?.id);
        return;
      }
      await sleep(500);
    }
    throw new Error("Dossier processing did not finish within the local demo timeout.");
  }

  async function runDossier() {
    setLoading(true);
    setError(undefined);
    setReport(null);
    try {
      let response: Response;
      if (files.length) {
        const form = new FormData();
        files.forEach((file) => form.append("files", file));
        response = await fetch(`${API_URL}/api/dossiers`, { method: "POST", body: form });
      } else {
        response = await fetch(`${API_URL}/api/dossiers/sample`, { method: "POST" });
      }
      if (!response.ok) throw new Error(await apiError(response));
      await waitForReport((await response.json()) as JobStatus);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The audit could not be started.");
    } finally {
      setLoading(false);
    }
  }

  async function syncCognee() {
    if (!jobId) return;
    setSyncing(true);
    setError(undefined);
    try {
      const response = await fetch(`${API_URL}/api/dossiers/${jobId}/cognee-sync`, { method: "POST" });
      if (!response.ok) throw new Error(await apiError(response));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Cognee sync failed.");
    } finally {
      setSyncing(false);
    }
  }

  const notTestable = report?.procedures.filter((item) => item.status === "not_testable") ?? [];

  return (
    <main className="flex min-h-screen bg-[var(--canvas)] text-[var(--ink)]">
      <AppSidebar integrations={integrations} dossierName={report?.dossier_name} />
      <div className="min-w-0 flex-1">
        <header className="flex h-[68px] items-center justify-between border-b border-[var(--line)] bg-white px-4 md:px-6">
          <div>
            <p className="text-sm font-semibold">Journal Entry Testing · Evidence Review</p>
            <p className="mt-1 text-xs text-[var(--muted)]">
              {report ? `${report.files_scanned} documents · ${report.tests_run} procedures completed` : "Local audit workspace"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {report && (
              <>
                <span className="result-chip passed">{report.suppressed_leads} suppressed</span>
                {notTestable.length > 0 && <span className="result-chip review">{notTestable.length} not testable</span>}
                <span className="result-chip failed">{report.findings.length} findings</span>
              </>
            )}
          </div>
        </header>

        <div className="space-y-4 p-4">
          <AgentBar
            loading={loading}
            syncing={syncing}
            canSync={Boolean(report && jobId && integrations?.cognee.configured)}
            fileCount={files.length}
            jobStatus={jobStatus}
            onFiles={setFiles}
            onRun={runDossier}
            onSync={syncCognee}
          />
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-800">{error}</div>
          )}
          {notTestable.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
              {notTestable.map((item) => `${item.rule_id}: ${item.reason}`).join(" · ")}
            </div>
          )}

          <section className="grid min-h-[calc(100vh-168px)] overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-sm lg:grid-cols-[minmax(420px,0.9fr)_minmax(500px,1.1fr)]">
            <FindingList
              findings={report?.findings ?? []}
              selectedId={selected?.id}
              onSelect={setSelectedId}
            />
            <EvidencePanel finding={selected} apiUrl={API_URL} jobId={jobId} />
          </section>

          <QuestionPanel apiUrl={API_URL} jobId={report ? jobId : undefined} />
        </div>
      </div>
    </main>
  );
}
