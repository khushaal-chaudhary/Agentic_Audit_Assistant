import type { IntegrationStatus, WorkspaceView } from "@/lib/types";

type Props = {
  integrations: IntegrationStatus | null;
  dossierName?: string;
  activeView: WorkspaceView;
  onSelect: (view: WorkspaceView) => void;
};

const workspaceItems: Array<[WorkspaceView, string, string]> = [
  ["overview", "◇", "Overview"],
  ["dossier", "▤", "Engagement"],
  ["documents", "▢", "Documents"],
  ["findings", "▦", "Findings"],
];

const analysisItems: Array<[WorkspaceView, string, string]> = [
  ["analysis", "◫", "Data analysis"],
  ["rules", "◈", "Deterministic rules"],
  ["review", "✓", "Report review"],
];

function NavigationGroup({
  items,
  activeView,
  onSelect,
}: {
  items: Array<[WorkspaceView, string, string]>;
  activeView: WorkspaceView;
  onSelect: (view: WorkspaceView) => void;
}) {
  return (
    <nav className="space-y-1">
      {items.map(([view, icon, label]) => {
        const active = activeView === view;
        return (
          <button
            aria-current={active ? "page" : undefined}
            className={
              "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-[13px] transition " +
              (active
                ? "bg-white font-semibold text-[var(--green)] shadow-sm"
                : "text-white/70 hover:bg-white/10 hover:text-white")
            }
            key={view}
            onClick={() => onSelect(view)}
          >
            <span className="w-5 text-center text-xs">{icon}</span>
            <span>{label}</span>
          </button>
        );
      })}
    </nav>
  );
}

export function AppSidebar({
  integrations,
  dossierName,
  activeView,
  onSelect,
}: Props) {
  return (
    <aside className="hidden h-screen w-[248px] shrink-0 flex-col bg-[var(--green)] px-[14px] py-[18px] text-white md:flex">
      <div className="flex items-center gap-3 px-1.5">
        <div className="grid h-[34px] w-[34px] place-items-center rounded-[9px] border border-white/20 bg-white/10 text-sm font-bold">
          A
        </div>
        <div className="leading-tight">
          <p className="text-[15px] font-bold tracking-[-0.01em]">AuditGraph</p>
          <p className="mt-0.5 text-[11px] text-white/50">Evidence workspace</p>
        </div>
      </div>

      <div className="mt-[18px] rounded-[10px] border border-white/10 bg-white/[0.08] px-3 py-2.5 text-[13px]">
        <div className="flex items-center gap-2">
          <span className="grid h-[18px] w-[18px] place-items-center rounded bg-[var(--mint)] text-[10px] font-bold text-[var(--green)]">
            A
          </span>
          Audit workspace
        </div>
      </div>

      <div className="mt-2.5 rounded-[10px] bg-black/15 px-3 py-2.5">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-white/45">
          Active dossier
        </p>
        <p className="mt-1 truncate text-[13px] font-medium">
          {dossierName ?? "No dossier loaded"}
        </p>
      </div>

      <div className="mt-4">
        <NavigationGroup
          items={workspaceItems}
          activeView={activeView}
          onSelect={onSelect}
        />
      </div>

      <p className="mb-2 mt-5 px-3 text-[10px] font-bold uppercase tracking-[0.14em] text-white/40">
        Audit agents
      </p>
      <NavigationGroup
        items={analysisItems}
        activeView={activeView}
        onSelect={onSelect}
      />

      <div className="mt-auto rounded-xl border border-white/10 bg-black/15 p-3 text-xs">
        <p className="mb-2 font-semibold">Connections</p>
        <div className="flex items-center justify-between py-1 text-white/60">
          <span>Cognee graph</span>
          <span className={integrations?.cognee.configured ? "text-[#8fd6a6]" : ""}>
            {integrations?.cognee.configured ? "● Connected" : "Local only"}
          </span>
        </div>
        <div className="flex items-center justify-between py-1 text-white/60">
          <span>OpenAI</span>
          <span className={integrations?.openai.configured ? "text-[#8fd6a6]" : ""}>
            {integrations?.openai.configured ? "● Connected" : "Local only"}
          </span>
        </div>
      </div>
    </aside>
  );
}
