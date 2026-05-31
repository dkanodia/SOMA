import React, { useMemo, useState, useEffect } from "react";
import NetworkGraph       from "./components/NetworkGraph";
import TimelinePanel      from "./components/TimelinePanel";
import IncidentPanel      from "./components/IncidentPanel";
import DefenseActionPanel from "./components/DefenseActionPanel";
import DriftPanel         from "./components/DriftPanel";
import HoneypotPanel      from "./components/HoneypotPanel";
import LayerRadarPanel    from "./components/LayerRadarPanel";
import EvasionPanel       from "./components/EvasionPanel";
import useWebSocket       from "./hooks/useWebSocket";
import "./styles/index.css";

const HOSTS = ["User0", "User1", "User2", "Enterprise0", "Enterprise1", "Op_Server0"];

// Base session time: today at 08:00 local
const SESSION_BASE = (() => {
  const d = new Date();
  d.setHours(8, 0, 0, 0);
  return d.getTime();
})();

function stepToTimestamp(step) {
  const t = new Date(SESSION_BASE + step * 30_000); // 30 s per step
  return t.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function stepToDate(step) {
  const t = new Date(SESSION_BASE + step * 30_000);
  return t.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

function actionLabel(actionName) {
  if (!actionName || actionName === "Monitor") return "Monitor";
  return actionName.replace("_", " ");
}

function getSeverity(state) {
  const score = state?.top_threat?.score ?? 0;
  if (score >= 0.75) return { label: "Critical", className: "critical" };
  if (score >= 0.45) return { label: "Elevated", className: "elevated" };
  if (state?.is_attack) return { label: "Investigating", className: "elevated" };
  return { label: "Nominal", className: "nominal" };
}

function incidentId(host, step) {
  // Deterministic ticket ID from host + step
  const n = (host.charCodeAt(0) * 31 + (step ?? 0)) % 9000 + 1000;
  return `INC-${n}`;
}

const NAV_ITEMS = [
  { id: "operations", label: "Operations",  icon: "⬡" },
  { id: "incidents",  label: "Incidents",   icon: "⚠" },
  { id: "assets",     label: "Assets",      icon: "□" },
  { id: "policies",   label: "Policies",    icon: "◈" },
  { id: "auditlog",   label: "Audit Log",   icon: "≡" },
];

function ConsoleSidebar({ connected, activeNav, setNav }) {
  const [clock, setClock] = React.useState(() =>
    new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
  );
  useEffect(() => {
    const t = setInterval(() =>
      setClock(new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }))
    , 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <aside className="console-sidebar">
      <div className="console-brand">
        <strong>SO<span>MA</span></strong>
        <small>Immune Defense Platform</small>
      </div>

      <nav className="console-nav" aria-label="Primary">
        {NAV_ITEMS.map(({ id, label, icon }) => (
          <button
            key={id}
            className={activeNav === id ? "active" : ""}
            onClick={() => setNav(id)}
          >
            <span className="nav-icon">{icon}</span>
            {label}
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="analyst-card">
          <div className="analyst-avatar">DK</div>
          <div>
            <strong>Analyst on duty</strong>
            <span>D. Kanodia</span>
          </div>
        </div>
        <div className="connection-card">
          <span className={connected ? "status-dot live" : "status-dot"} />
          <div>
            <strong>{connected ? "Live feed" : "Session replay"}</strong>
            <span>{connected ? clock : "Historical analysis"}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

function TopBar({ state, step, activeNav }) {
  const severity = getSeverity(state);
  const topHost  = state?.top_threat?.host ?? "—";
  const action   = actionLabel(state?.orchestrator?.action_name);
  const ts       = stepToTimestamp(step);
  const date     = stepToDate(step);

  return (
    <header className="topbar">
      <div className="topbar-title">
        <p>SOMA / {NAV_ITEMS.find((n) => n.id === activeNav)?.label ?? "Operations"}</p>
        <h1>Security Operations Center</h1>
      </div>
      <div className="topbar-metrics">
        <div className={`metric ${severity.className}`}>
          <span>Posture</span>
          <strong>{severity.label}</strong>
        </div>
        <div className="metric">
          <span>Priority host</span>
          <strong>{topHost}</strong>
        </div>
        <div className="metric action">
          <span>Recommended action</span>
          <strong>{action}</strong>
        </div>
      </div>
      <div className="topbar-clock">
        <div className="clock-time">{ts}</div>
        <div className="clock-date">{date}</div>
      </div>
    </header>
  );
}

function IncidentQueue({ state, onSelectHost, selectedHost, step }) {
  const incidents = state?.incidents ?? [];
  const rows = incidents.length
    ? incidents
    : HOSTS.map((host) => ({
        host,
        confidence: "CLEAR",
        score: 0,
        attack_type: "No threats detected",
        explanation: "All systems nominal",
      }));

  return (
    <section className="panel queue-panel">
      <div className="section-head">
        <div>
          <span>Incident queue</span>
          <strong>{incidents.length ? `${incidents.length} active` : "All clear"}</strong>
        </div>
        <button className="small-button">Filter</button>
      </div>
      <div className="queue-list">
        {rows.slice(0, 8).map((inc) => (
          <button
            key={`${inc.host}-${inc.attack_type}`}
            className={`queue-row ${selectedHost === inc.host ? "selected" : ""} ${inc.confidence?.toLowerCase()}`}
            onClick={() => onSelectHost(inc.host)}
          >
            <div className="queue-row-top">
              <span className="host-name">{inc.host}</span>
              <span className={`inc-conf ${inc.confidence}`}>{inc.confidence}</span>
            </div>
            <span className="queue-desc">{inc.attack_type?.replaceAll("_", " ")}</span>
            {inc.layers_fired?.length > 0 && (
              <div className="layers-fired">
                {inc.layers_fired.map((l) => (
                  <span key={l} className={`layer-chip layer-chip-${l.replace("_", "-")}`}>{l.replace("_", " ")}</span>
                ))}
              </div>
            )}
            <div className="queue-row-foot">
              <span className="queue-ticket">{incidentId(inc.host, step)}</span>
              <span className="queue-score">{inc.score ? inc.score.toFixed(3) : "—"}</span>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

const LAYER_META = [
  {
    id:   "innate",
    name: "Innate Immunity",
    bio:  "Isolation Forest · fast non-specific detection",
  },
  {
    id:   "adaptive",
    name: "Adaptive Response",
    bio:  "PPO agent · targeted learned defence",
  },
  {
    id:   "tolerance",
    name: "Immune Tolerance",
    bio:  "Role baseline · suppresses false positives",
  },
  {
    id:   "memory",
    name: "Immunological Memory",
    bio:  "Long-dwell drift · centroid trajectory",
  },
  {
    id:   "learned",
    name: "Clonal Selection",
    bio:  "VAE gallery · attack-type recognition",
  },
];

function ImmuneResponsePanel({ state }) {
  const orch           = state?.orchestrator ?? {};
  const anomalyScores  = state?.anomaly_scores ?? {};
  const threshold      = state?.innate_threshold ?? 0.5;
  const tolSuppressed  = state?.tolerance_suppressed ?? [];
  const tolBreached    = state?.tolerance_breached ?? [];
  const driftAlarms    = state?.drift_alarms ?? {};
  const driftingHosts  = Object.entries(driftAlarms).filter(([, v]) => v).map(([h]) => h);
  const laConf         = state?.learned_attack_conf ?? 0;
  const laType         = (state?.learned_attack_type ?? "unknown").replaceAll("_", " ");
  const topInnate      = Object.entries(anomalyScores).sort((a, b) => b[1] - a[1])[0];
  const maxScore       = topInnate?.[1] ?? 0;

  const layers = [
    {
      id:     "innate",
      status: state?.innate_fired ? "firing" : "quiet",
      detail: state?.innate_fired
        ? `${topInnate?.[0]} · score ${maxScore.toFixed(2)} (threshold ${threshold.toFixed(2)})`
        : `Max ${maxScore.toFixed(2)} · below threshold ${threshold.toFixed(2)}`,
    },
    {
      id:     "adaptive",
      status: orch.action_name && orch.action_name !== "Monitor" ? "responding" : "monitoring",
      detail: orch.action_name
        ? `${orch.action_name.replaceAll("_", " ")}${orch.host ? ` → ${orch.host}` : ""}`
        : "Monitoring — no action required",
    },
    {
      id:     "tolerance",
      status: tolBreached.length ? "breach" : tolSuppressed.length ? "active" : "quiet",
      detail: [
        tolBreached.length   ? `Role breach: ${tolBreached.join(", ")}` : null,
        tolSuppressed.length ? `Tolerated: ${tolSuppressed.join(", ")}` : null,
      ].filter(Boolean).join(" · ") || "All hosts within role baseline",
    },
    {
      id:     "memory",
      status: driftingHosts.length ? "alarm" : "quiet",
      detail: driftingHosts.length
        ? `Long-dwell drift: ${driftingHosts.join(", ")}`
        : "All hosts within baseline centroid",
    },
    {
      id:     "learned",
      status: laConf > 0.5 ? "firing" : laConf > 0.3 ? "low" : "quiet",
      detail: laConf > 0.3
        ? `${laType} · ${(laConf * 100).toFixed(0)}% match`
        : "No gallery match",
    },
  ];

  const statusLabel = {
    firing:     "Firing",
    responding: "Responding",
    breach:     "Breach",
    alarm:      "Alarm",
    active:     "Active",
    monitoring: "Monitoring",
    low:        "Weak signal",
    quiet:      "Quiet",
  };

  return (
    <section className="panel immune-panel">
      <div className="section-head">
        <div>
          <span>Immune response stack</span>
          <strong>SOMA · 5 layers active</strong>
        </div>
        <span className={`conf-badge ${(orch.confidence ?? "NONE").toLowerCase()}`}>
          {orch.confidence ?? "NONE"}
        </span>
      </div>

      <div className="immune-layers">
        {LAYER_META.map((lm) => {
          const l = layers.find((x) => x.id === lm.id);
          return (
            <div key={lm.id} className={`immune-layer layer-${l.status}`}>
              <div className="layer-top">
                <span className="layer-name">{lm.name}</span>
                <span className="layer-badge">{statusLabel[l.status] ?? l.status}</span>
              </div>
              <span className="layer-bio">{lm.bio}</span>
              <span className="layer-detail">{l.detail}</span>
            </div>
          );
        })}
      </div>

      <div className="fusion-bar">
        <span className="fusion-label">Fusion output</span>
        <strong className="fusion-action">
          {orch.action_name?.replaceAll("_", " ") ?? "Monitor"}
        </strong>
        <p className="fusion-reason">
          {orch.reason ?? "No active threats — continuing passive observation."}
        </p>
      </div>
    </section>
  );
}

function AssetTable({ state, selectedHost, onSelectHost }) {
  const compromised = new Set(state?.compromised_hosts ?? []);
  const driftScores = state?.drift_scores ?? {};
  const hostScores = state?.host_innate_scores ?? {};
  const breached = new Set(state?.tolerance_breached ?? []);
  const suppressed = new Set(state?.tolerance_suppressed ?? []);

  return (
    <section className="panel asset-panel">
      <div className="section-head">
        <div>
          <span>Protected assets</span>
          <strong>{HOSTS.length} hosts</strong>
        </div>
        <button className="small-button">Export</button>
      </div>
      <div className="asset-table">
        <div className="asset-row asset-header">
          <span>Host</span>
          <span>Status</span>
          <span>Anomaly</span>
          <span>Drift</span>
        </div>
        {HOSTS.map((host) => {
          const status = compromised.has(host)
            ? "Compromised"
            : breached.has(host)
              ? "Role breach"
              : suppressed.has(host)
                ? "Tolerated"
                : "Healthy";
          return (
            <button
              key={host}
              className={`asset-row ${selectedHost === host ? "selected" : ""}`}
              onClick={() => onSelectHost(host)}
            >
              <span>{host}</span>
              <span className={`asset-status ${status.toLowerCase().replace(" ", "-")}`}>{status}</span>
              <span>{(hostScores[host] ?? 0).toFixed(2)}</span>
              <span>{(driftScores[host] ?? 0).toFixed(1)}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function EvidenceTabs({ state, meta, step, setStep }) {
  const [tab, setTab] = useState("timeline");
  return (
    <section className="panel evidence-panel">
      <div className="tab-strip">
        {[
          ["timeline",  "Timeline"],
          ["incidents", "Incidents"],
          ["actions",   "Actions"],
          ["drift",     "Drift"],
          ["decoys",    "Decoys"],
          ["layers",    "Layers"],
          ["evasion",   "Evasion"],
        ].map(([id, label]) => (
          <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      <div className="evidence-body">
        {tab === "timeline"  && <TimelinePanel state={state} meta={meta} currentStep={step} onStepClick={setStep} />}
        {tab === "incidents" && <IncidentPanel state={state} step={step} />}
        {tab === "actions"   && <DefenseActionPanel state={state} meta={meta} step={step} />}
        {tab === "drift"     && <DriftPanel state={state} meta={meta} />}
        {tab === "decoys"    && <HoneypotPanel state={state} />}
        {tab === "layers"    && <LayerRadarPanel state={state} meta={meta} />}
        {tab === "evasion"   && <EvasionPanel meta={meta} />}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Secondary views (Incidents / Assets / Policies / Audit Log)
// ---------------------------------------------------------------------------

function IncidentsView({ meta, step }) {
  const allSteps = meta?._steps ?? [];
  const [filter, setFilter] = useState("ALL");

  // Collect every incident across all steps, label with step
  const allIncidents = useMemo(() => {
    const out = [];
    allSteps.forEach((s) => {
      (s.incidents ?? []).forEach((inc) => {
        out.push({ ...inc, _step: s.step, _time: stepToTimestamp(s.step) });
      });
    });
    return out.reverse();   // most recent first
  }, [allSteps]);

  const conf_order = { HIGH: 0, MEDIUM: 1, LOW: 2, CLEAR: 3 };
  const filtered = filter === "ALL" ? allIncidents
    : allIncidents.filter((i) => i.confidence === filter);

  return (
    <div className="view-page">
      <div className="view-header">
        <div>
          <p className="view-breadcrumb">SOMA / Incidents</p>
          <h1 className="view-title">Incident History</h1>
        </div>
        <div className="view-filters">
          {["ALL", "HIGH", "MEDIUM", "LOW"].map((f) => (
            <button key={f} className={`filter-btn ${filter === f ? "active" : ""}`}
              onClick={() => setFilter(f)}>{f}</button>
          ))}
        </div>
      </div>

      <div className="view-table-wrap">
        <div className="view-table-head view-incident-row">
          <span>Time</span><span>Host</span><span>Confidence</span>
          <span>Score</span><span>Layers fired</span><span>Type</span><span>Explanation</span>
        </div>
        <div className="view-table-body">
          {filtered.length === 0 && (
            <p className="panel-placeholder">No incidents match filter.</p>
          )}
          {filtered.map((inc, i) => (
            <div key={i} className={`view-incident-row inc-row-${inc.confidence?.toLowerCase()}`}>
              <span className="mono-sm">{inc._time}</span>
              <span className="fw-bold">{inc.host}</span>
              <span className={`inc-conf ${inc.confidence}`}>{inc.confidence}</span>
              <span className="mono-sm">{inc.score?.toFixed(3)}</span>
              <span className="mono-sm">{(inc.layers_fired ?? []).join(", ") || "—"}</span>
              <span className="mono-sm">{inc.attack_type ?? "—"}</span>
              <span className="fg-3-sm">{inc.explanation ?? "—"}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function AssetsView({ state }) {
  const compromised  = new Set(state?.compromised_hosts ?? []);
  const breached     = new Set(state?.tolerance_breached ?? []);
  const suppressed   = new Set(state?.tolerance_suppressed ?? []);
  const driftAlarms  = state?.drift_alarms ?? {};
  const driftScores  = state?.drift_scores ?? {};
  const anomScores   = state?.host_innate_scores ?? {};
  const honeypot     = state?.honeypot_flags ?? {};

  const hostRoles = {
    User0: "Workstation", User1: "Workstation", User2: "Workstation",
    Enterprise0: "Enterprise Server", Enterprise1: "Enterprise Server",
    Op_Server0: "Operations Server",
  };

  return (
    <div className="view-page">
      <div className="view-header">
        <div>
          <p className="view-breadcrumb">SOMA / Assets</p>
          <h1 className="view-title">Protected Assets</h1>
        </div>
        <div className="view-filters">
          <span className="stat-chip">{HOSTS.length} monitored</span>
          <span className="stat-chip alert">{compromised.size} compromised</span>
          <span className="stat-chip warn">{breached.size} role breach</span>
        </div>
      </div>

      <div className="view-table-wrap">
        <div className="view-table-head view-asset-row">
          <span>Host</span><span>Role</span><span>Status</span>
          <span>Innate score</span><span>Drift</span><span>Drift alarm</span>
          <span>Tolerance</span><span>Decoy active</span>
        </div>
        <div className="view-table-body">
          {HOSTS.map((host) => {
            const status = compromised.has(host) ? "Compromised"
              : breached.has(host) ? "Role breach"
              : suppressed.has(host) ? "Tolerated"
              : "Healthy";
            return (
              <div key={host} className="view-asset-row">
                <span className="fw-bold">{host}</span>
                <span className="fg-3-sm">{hostRoles[host] ?? "—"}</span>
                <span className={`asset-status ${status.toLowerCase().replace(" ", "-")}`}>{status}</span>
                <span className="mono-sm">{(anomScores[host] ?? 0).toFixed(3)}</span>
                <span className="mono-sm">{(driftScores[host] ?? 0).toFixed(3)}</span>
                <span className={`asset-status ${driftAlarms[host] ? "compromised" : "healthy"}`}>
                  {driftAlarms[host] ? "Alarm" : "Normal"}
                </span>
                <span className={`asset-status ${suppressed.has(host) ? "tolerated" : breached.has(host) ? "role-breach" : "healthy"}`}>
                  {suppressed.has(host) ? "Suppressed" : breached.has(host) ? "Breached" : "Normal"}
                </span>
                <span className={`asset-status ${honeypot[host] ? "role-breach" : "healthy"}`}>
                  {honeypot[host] ? "Active" : "Inactive"}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function PoliciesView({ meta }) {
  const innateThresh = meta?.innate_threshold ?? 0.5;
  const memThresh    = meta?.memory_threshold ?? 1.0;

  const policies = [
    {
      layer: "Layer 1 — Innate Immunity",
      model: "Isolation Forest",
      params: [
        { key: "Anomaly threshold (θ_inn)", value: innateThresh.toFixed(3) },
        { key: "Per-host scoring", value: "Enabled" },
        { key: "FPR target", value: "≤ 5% fused" },
      ],
      desc: "Fast, non-specific detection. Fires on any host whose anomaly score exceeds θ_inn. Single-layer incidents below HIGH confidence require a second layer to confirm.",
    },
    {
      layer: "Layer 2 — Adaptive Response",
      model: "PPO (Stable-Baselines3)",
      params: [
        { key: "Action space", value: "Discrete(19)" },
        { key: "Actions", value: "Monitor, Analyze, Remove, Restore × 6 hosts" },
        { key: "Reward", value: "+1 clean, −1 compromised" },
      ],
      desc: "Reinforcement-learned policy. Selects targeted defender actions each step. Runs in parallel with heuristic orchestrator.",
    },
    {
      layer: "Layer 3 — Immune Tolerance",
      model: "Role-baseline z-score",
      params: [
        { key: "Suppression", value: "Hosts within 2σ of role baseline" },
        { key: "Breach", value: "Hosts exceeding role baseline by > 3σ" },
        { key: "Calibration", value: "600 clean steps" },
      ],
      desc: "Prevents false positives for normal host behaviour. Suppresses innate alerts on tolerated hosts. Flags role violations as breaches.",
    },
    {
      layer: "Layer 3b — Deception / Honeypot",
      model: "Heuristic trigger",
      params: [
        { key: "Trigger threshold", value: "Anomaly score > 0.70" },
        { key: "Mode", value: "Heuristic (B_lineAgent ignores signals)" },
      ],
      desc: "Signals decoy deployment when innate anomaly score exceeds threshold. Game-theoretic signaling policy (PBE) is trained separately — not applied to B_lineAgent which ignores signals.",
    },
    {
      layer: "Layer 4 — Immunological Memory",
      model: "Long-dwell centroid drift",
      params: [
        { key: "Drift threshold (θ_mem)", value: memThresh.toFixed(3) },
        { key: "Window", value: "Rolling 10-step centroid" },
        { key: "Metric", value: "L2 norm of centroid displacement" },
      ],
      desc: "Detects persistent, slow-moving attackers that evade innate detection. Tracks centroid trajectory per host; alarms when displacement exceeds θ_mem.",
    },
    {
      layer: "Layer 5 — Clonal Selection",
      model: "VAE gallery (cosine similarity)",
      params: [
        { key: "Latent dim", value: "4" },
        { key: "Gallery", value: "4 attack prototypes" },
        { key: "Match threshold", value: "Confidence > 0.30" },
      ],
      desc: "Variational autoencoder encodes rolling observation window into latent space. Matched against gallery of known attack signatures via cosine similarity.",
    },
    {
      layer: "Fusion — NetworkImmuneCorrelator",
      model: "Weighted multi-layer gate",
      params: [
        { key: "Innate weight", value: "0.30" },
        { key: "Memory weight", value: "0.30" },
        { key: "Tolerance breach weight", value: "0.20" },
        { key: "Learned attacks weight", value: "0.20" },
        { key: "Gate", value: "≥ 2 layers OR score ≥ 0.50" },
      ],
      desc: "Aggregates all layer signals. Single-layer innate-only alarms are suppressed (primary FPR source). Multi-layer confirmation required for incidents to surface.",
    },
  ];

  return (
    <div className="view-page">
      <div className="view-header">
        <div>
          <p className="view-breadcrumb">SOMA / Policies</p>
          <h1 className="view-title">Immune Layer Configuration</h1>
        </div>
      </div>
      <div className="policy-grid">
        {policies.map((p) => (
          <div key={p.layer} className="policy-card">
            <div className="policy-header">
              <span className="policy-layer">{p.layer}</span>
              <span className="policy-model">{p.model}</span>
            </div>
            <p className="policy-desc">{p.desc}</p>
            <div className="policy-params">
              {p.params.map((param) => (
                <div key={param.key} className="policy-param">
                  <span className="param-key">{param.key}</span>
                  <span className="param-val">{param.value}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AuditLogView({ meta, step }) {
  const allSteps = meta?._steps ?? [];

  const BLUE_ACTIONS = [
    "Monitor",
    "Analyze_User0", "Analyze_User1", "Analyze_User2",
    "Analyze_Enterprise0", "Analyze_Enterprise1", "Analyze_Op_Server0",
    "Remove_User0", "Remove_User1", "Remove_User2",
    "Remove_Enterprise0", "Remove_Enterprise1", "Remove_Op_Server0",
    "Restore_User0", "Restore_User1", "Restore_User2",
    "Restore_Enterprise0", "Restore_Enterprise1", "Restore_Op_Server0",
  ];

  const ACTION_COLORS = { Remove: "#A83D2E", Analyze: "#B87030", Restore: "#6452A0", Monitor: "#3E3D3A" };

  const logSteps = useMemo(() => [...allSteps].slice(0, step + 1).reverse(), [allSteps, step]);

  return (
    <div className="view-page">
      <div className="view-header">
        <div>
          <p className="view-breadcrumb">SOMA / Audit Log</p>
          <h1 className="view-title">Defense Action Log</h1>
        </div>
        <span className="stat-chip">{logSteps.length} events</span>
      </div>

      <div className="view-table-wrap">
        <div className="view-table-head view-audit-row">
          <span>Time</span><span>Step</span><span>PPO Action</span>
          <span>Orchestrator</span><span>Confidence</span><span>Reward</span><span>Reason</span>
        </div>
        <div className="view-table-body">
          {logSteps.map((s, i) => {
            const actionName = BLUE_ACTIONS[s.action] ?? "Monitor";
            const prefix = actionName.split("_")[0];
            const color = ACTION_COLORS[prefix] ?? "#64748b";
            const orch = s.orchestrator ?? {};
            return (
              <div key={i} className="view-audit-row" style={{ borderLeft: `3px solid ${color}22` }}>
                <span className="mono-sm">{stepToTimestamp(s.step)}</span>
                <span className="mono-sm">{s.step}</span>
                <span style={{ fontFamily: "var(--mono)", fontSize: "0.68rem", color }}>{actionName}</span>
                <span className="mono-sm">{orch.action_name ?? "—"}</span>
                <span className={`inc-conf ${orch.confidence ?? "NONE"}`}>{orch.confidence ?? "—"}</span>
                <span className="mono-sm" style={{ color: s.reward >= 0 ? "var(--ok)" : "var(--alert)" }}>
                  {s.reward?.toFixed(2) ?? "—"}
                </span>
                <span className="fg-3-sm">{orch.reason ?? "—"}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/**
 * Normalize raw WebSocket/JSON payload into fields all components expect.
 *
 * Raw payload uses:
 *   anomaly_scores   — {host: float} per-host IF scores
 *   centroid_pos     — {host: [x,y]|null} per-host memory centroid
 *   host_states      — {host: {activity,compromised,sessions,processes}}
 *
 * Components additionally expect:
 *   anomaly_score     — single float (max across hosts), for radar/timeline
 *   host_innate_scores— alias of anomaly_scores
 *   drift_scores      — {host: float} L2 norm of centroid (for timeline/radar/asset)
 *   compromised_hosts — [host] where host_states.compromised > 0.5
 */
function enrichState(raw) {
  if (!raw) return null;

  const anomalyScores = raw.anomaly_scores ?? {};
  const anomalyScore  = Object.values(anomalyScores).length
    ? Math.max(...Object.values(anomalyScores))
    : 0;

  const driftScores = {};
  for (const [h, pos] of Object.entries(raw.centroid_pos ?? {})) {
    driftScores[h] = pos ? Math.sqrt(pos[0] ** 2 + pos[1] ** 2) : 0;
  }

  const compromisedHosts = Object.entries(raw.host_states ?? {})
    .filter(([, v]) => (v?.compromised ?? 0) > 0.5)
    .map(([h]) => h);

  return {
    ...raw,
    anomaly_score:      anomalyScore,
    host_innate_scores: anomalyScores,
    drift_scores:       driftScores,
    compromised_hosts:  compromisedHosts,
  };
}

export default function App() {
  const {
    state, meta, step, totalSteps, connected, setStep,
  } = useWebSocket(process.env.REACT_APP_WS_URL || "ws://localhost:8765");

  const currentState = enrichState(state) ?? {};
  const [selectedHost, setSelectedHost] = useState("Op_Server0");
  const [activeNav, setActiveNav] = useState("operations");

  const compromisedCount = currentState.compromised_hosts?.length ?? 0;
  const incidentCount    = currentState.incidents?.length ?? 0;
  const learnedType      = currentState.learned_attack_type && currentState.learned_attack_type !== "unknown"
    ? currentState.learned_attack_type.replaceAll("_", " ")
    : "Unclassified";
  const layersFiring = [
    currentState?.innate_fired,
    currentState?.orchestrator?.action_name && currentState.orchestrator.action_name !== "Monitor",
    (currentState?.tolerance_breached?.length ?? 0) > 0,
    Object.values(currentState?.drift_alarms ?? {}).some(Boolean),
    (currentState?.learned_attack_conf ?? 0) > 0.3,
  ].filter(Boolean).length;

  const summary = useMemo(() => [
    { label: "Layers active",      value: `${layersFiring} / 5` },
    { label: "Compromised hosts",  value: compromisedCount },
    { label: "Fused incidents",    value: incidentCount },
    { label: "Attack signature",   value: learnedType },
  ], [layersFiring, compromisedCount, incidentCount, learnedType]);

  return (
    <div className="app-root">
      <ConsoleSidebar connected={connected} activeNav={activeNav} setNav={setActiveNav} />
      <main className="console-main">
        <TopBar state={currentState} step={step} activeNav={activeNav} />

        {/* ── Non-Operations views fill the remaining space ── */}
        {activeNav === "incidents" && (
          <div className="view-scroll"><IncidentsView meta={meta} step={step} /></div>
        )}
        {activeNav === "assets" && (
          <div className="view-scroll"><AssetsView state={currentState} /></div>
        )}
        {activeNav === "policies" && (
          <div className="view-scroll"><PoliciesView meta={meta} /></div>
        )}
        {activeNav === "auditlog" && (
          <div className="view-scroll"><AuditLogView meta={meta} step={step} /></div>
        )}

        {/* ── Operations view ── */}
        {activeNav === "operations" && <>
          <div className="summary-strip">
            {summary.map((item) => (
              <div key={item.label}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>

          <div className="ops-grid">
            <IncidentQueue state={currentState} selectedHost={selectedHost} onSelectHost={setSelectedHost} step={step} />

            <section className="panel map-panel">
              <div className="section-head">
                <div>
                  <span>Network topology</span>
                  <strong>{selectedHost}</strong>
                </div>
                <span className="map-phase">{stepToTimestamp(step)}</span>
              </div>
              <NetworkGraph state={currentState} meta={meta} />
            </section>

            <ImmuneResponsePanel state={currentState} />

            <AssetTable state={currentState} selectedHost={selectedHost} onSelectHost={setSelectedHost} />

            <EvidenceTabs state={currentState} meta={meta} step={step} setStep={setStep} />
          </div>
        </>}

        <div className="status-bar">
          <span className={connected ? "live-pill live" : "live-pill replay"}>
            <span className="live-dot" />
            {connected ? "Live" : "Replaying session"}
          </span>
          <span className="sb-sep" />
          <span className="sb-item">{stepToTimestamp(step)}</span>
          <span className="sb-sep" />
          <span className="sb-item">{step + 1} of {Math.max(totalSteps, 1)} events</span>
          <span className="sb-sep" />
          <span className="sb-item">{totalSteps > 0 ? `${HOSTS.length} hosts monitored` : "Connecting…"}</span>
        </div>
      </main>
    </div>
  );
}
