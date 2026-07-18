import type { JobStatus } from "@/lib/types";

type Props = {
  loading: boolean;
  syncing: boolean;
  canSync: boolean;
  fileCount: number;
  jobStatus: JobStatus | null;
  onFiles: (files: File[]) => void;
  onRunSample: () => void;
  onRunFinal: () => void;
  onRunUpload: () => void;
  onSync: () => void;
};

export function AgentBar({
  loading,
  syncing,
  canSync,
  fileCount,
  jobStatus,
  onFiles,
  onRunSample,
  onRunFinal,
  onRunUpload,
  onSync,
}: Props) {
  const detail = loading && jobStatus
    ? `${jobStatus.message} · ${jobStatus.progress}%`
    : fileCount
      ? `${fileCount} local source file(s) selected · ZIP recommended`
      : "Choose a preloaded dossier or upload a ZIP that preserves its folder structure";

  return (
    <section className="overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-sm">
      <div className="flex flex-wrap items-center gap-3 p-3">
        <div className="min-w-[260px] flex-1 px-2">
          <p className="text-sm font-medium">
            {loading ? "Reconciling documents and building evidence chains…" : "What should AuditGraph investigate?"}
          </p>
          <p className="mt-1 text-xs text-[var(--muted)]">{detail}</p>
        </div>
        <label className="cursor-pointer rounded-lg border border-[var(--line-strong)] px-3 py-2 text-xs font-semibold hover:bg-[var(--soft)]">
          <input
            className="hidden"
            type="file"
            multiple
            accept=".zip,.csv,.txt,.xlsx,.docx,.pdf"
            onChange={(event) => onFiles(Array.from(event.target.files ?? []))}
          />
          + Add source
        </label>
        <button
          className="rounded-lg border border-[var(--line-strong)] px-3 py-2 text-xs font-semibold disabled:opacity-40"
          disabled={!canSync || syncing}
          onClick={onSync}
        >
          {syncing ? "Syncing…" : "Sync graph"}
        </button>
        {fileCount ? (
          <button
            className="rounded-lg bg-[var(--ink)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40"
            onClick={onRunUpload}
            disabled={loading}
          >
            {loading ? "Running…" : "Analyze upload ↑"}
          </button>
        ) : (
          <>
            <button
              className="rounded-lg border border-[var(--line-strong)] px-4 py-2 text-xs font-semibold hover:bg-[var(--soft)] disabled:opacity-40"
              onClick={onRunSample}
              disabled={loading}
            >
              Run sample dataset
            </button>
            <button
              className="rounded-lg bg-[var(--ink)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40"
              onClick={onRunFinal}
              disabled={loading}
            >
              {loading ? "Running…" : "Run final dataset ↑"}
            </button>
          </>
        )}
      </div>
      {loading && (
        <div className="h-1 bg-[var(--soft)]">
          <div
            className="h-full bg-[var(--mint-strong)] transition-all duration-500"
            style={{ width: `${jobStatus?.progress ?? 5}%` }}
          />
        </div>
      )}
    </section>
  );
}
