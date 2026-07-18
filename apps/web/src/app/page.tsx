"use client";

import { useEffect, useMemo, useState } from "react";

import { AgentBar } from "@/components/agent-bar";
import { AppSidebar } from "@/components/app-sidebar";
import { EvidencePanel } from "@/components/evidence-panel";
import { FindingList } from "@/components/finding-list";
import type { IntegrationStatus, Report } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {
  const [report, setReport] = useState<Report | null>(null);
  const [selectedId, setSelectedId] = useState<string>();
  const [integrations, setIntegrations] = useState<IntegrationStatus | null>(null);
  const [files, setFiles] = useState<File[]>([]);
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

  async function runDemo() {
    setLoading(true);
    setError(undefined);
    try {
      const response = await fetch(`${API_URL}/api/demo/analyze`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as Report;
      setReport(data);
      setSelectedId(data.findings[0]?.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The audit could not be started.");
    } finally {
      setLoading(false);
    }
  }

  async function syncCognee() {
    setSyncing(true);
    setError(undefined);
    try {
      const response = await fetch(`${API_URL}/api/demo/cognee-sync`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Cognee sync failed.");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <main className="flex min-h-screen bg-[var(--canvas)] text-[var(--ink)]">
      <AppSidebar integrations={integrations} />
      <div className="min-w-0 flex-1">
        <header className="flex h-[68px] items-center justify-between border-b border-[var(--line)] bg-white px-6">
          <div>
            <p className="text-sm font-semibold">Journal Entry Testing · FY 2025</p>
            <p className="mt-1 text-xs text-[var(--muted)]">
              {report ? `${report.files_scanned} documents · ${report.tests_run} procedures completed` : "Evidence review workspace"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {report && (
              <>
                <span className="result-chip passed">{report.suppressed_leads} suppressed</span>
                <span className="result-chip failed">{report.findings.length} findings</span>
              </>
            )}
            <button className="rounded-lg border border-[var(--line)] px-3 py-2 text-xs font-semibold">Export⌄</button>
          </div>
        </header>

        <div className="space-y-4 p-4">
          <AgentBar
            loading={loading}
            syncing={syncing}
            canSync={Boolean(report && integrations?.cognee.configured)}
            fileCount={files.length}
            onFiles={setFiles}
            onRun={runDemo}
            onSync={syncCognee}
          />
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-800">{error}</div>
          )}

          <section className="grid min-h-[calc(100vh-168px)] overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-sm lg:grid-cols-[minmax(420px,0.9fr)_minmax(500px,1.1fr)]">
            <FindingList
              findings={report?.findings ?? []}
              selectedId={selected?.id}
              onSelect={setSelectedId}
            />
            <EvidencePanel finding={selected} />
          </section>
        </div>
      </div>
    </main>
  );
}

