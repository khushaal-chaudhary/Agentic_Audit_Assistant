type Props = {
  loading: boolean;
  syncing: boolean;
  canSync: boolean;
  fileCount: number;
  onFiles: (files: File[]) => void;
  onRun: () => void;
  onSync: () => void;
};

export function AgentBar({
  loading,
  syncing,
  canSync,
  fileCount,
  onFiles,
  onRun,
  onSync,
}: Props) {
  return (
    <section className="rounded-2xl border border-[var(--line)] bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-[260px] flex-1 px-2">
          <p className="text-sm font-medium">
            {loading ? "Reconciling documents and building evidence chains…" : "What should AuditGraph investigate?"}
          </p>
          <p className="mt-1 text-xs text-[var(--muted)]">
            {fileCount ? `${fileCount} local source file(s) selected` : "Run the sample dossier or add source files"}
          </p>
        </div>
        <label className="cursor-pointer rounded-lg border border-[var(--line-strong)] px-3 py-2 text-xs font-semibold hover:bg-[var(--soft)]">
          <input
            className="hidden"
            type="file"
            multiple
            onChange={(event) => onFiles(Array.from(event.target.files ?? []))}
          />
          ＋ Add source
        </label>
        <button
          className="rounded-lg border border-[var(--line-strong)] px-3 py-2 text-xs font-semibold disabled:opacity-40"
          disabled={!canSync || syncing}
          onClick={onSync}
        >
          {syncing ? "Syncing…" : "Sync graph"}
        </button>
        <button
          className="rounded-lg bg-[var(--ink)] px-4 py-2 text-xs font-semibold text-white"
          onClick={onRun}
          disabled={loading}
        >
          {loading ? "Running…" : "Run agent ↑"}
        </button>
      </div>
    </section>
  );
}

