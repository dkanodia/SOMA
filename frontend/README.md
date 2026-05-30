# `frontend/` — React Demo UI

Live demo visualization for SOMA. Five panels displaying episode state in real time via WebSocket connection to `scripts/demo.py`.

---

## Quick start

```bash
cd frontend
npm install
npm start          # opens http://localhost:3000
```

Backend must be running first:
```bash
# In a separate terminal
python scripts/demo.py
```

If backend is unavailable, the UI falls back to static JSON replay from `results/demo_episode.json`.

---

## Layout

```
┌─────────────────────────────────────────────────────┐
│  SOMA  ·  Signaling-Optimal Memory Architecture  ●LIVE│
├────────────────────┬────────────────────────────────┤
│                    │                                 │
│   NetworkGraph     │    ConvergencePanel ★           │
│   (center, D3)     │    (largest panel, hero visual) │
│                    │                                 │
├────────────────────┴────────────────────────────────┤
│  AnomalyPanel      │  LearningPanel  │  DriftPanel  │
│  (Layer 1 scores)  │  (Layer 2 PPO)  │  (Layer 4)   │
└────────────────────┴─────────────────┴──────────────┘
```

CSS Grid handles the layout. `panel--hero` spans the right half of the top row. `panel--network` takes the left half. Bottom row is three equal columns.

---

## Color system (CSS variables in `src/styles/index.css`)

**Match these exactly in all components. Do not hardcode hex values — always use var().**

| Variable | Value | Used for |
|---|---|---|
| `--healthy` | `#22d3ee` | Healthy hosts, RL lines |
| `--compromised` | `#ef4444` | Compromised hosts |
| `--honeypot` | `#f59e0b` | Honeypot-activated hosts (heuristic) |
| `--pbe-line` | `#a855f7` | PBE equilibrium line |
| `--rl-line` | `#22d3ee` | Learned RL policy line |
| `--bg` | `#0a0e1a` | Page background |
| `--surface` | `#111827` | Panel backgrounds |
| `--muted` | `#64748b` | Axis labels, secondary text |
| `--text` | `#e2e8f0` | Primary text |

---

## WebSocket message format

Every frame sent from `demo.py` is a JSON object:

```typescript
interface DemoFrame {
  step:           number;
  hosts:          HostState[];
  anomaly_scores: Record<string, number>;   // host_name → raw score
  honeypot_flags: Record<string, boolean>;  // host_name → heuristic trigger
  drift_alarms:   Record<string, boolean>;  // host_name → long-dwell alarm
  honeypot_note:  string;                   // always "heuristic trigger — not signaling game policy"
  reward:         number;                   // current step reward
  convergence?:   ConvergenceData;          // sent periodically (not every frame)
}

interface HostState {
  id:           string;    // "User0", "Enterprise0", etc.
  compromised:  boolean;
  anomaly_score: number;
  honeypot:     boolean;
  drift_alarm:  boolean;
}

interface ConvergenceData {
  kappa:          number;
  learned_r:      number;
  pbe_r_star:     number;
  training_steps: number;
}
```

---

## `src/hooks/useWebSocket.js` — complete this

The hook connects to `ws://localhost:8765` and exposes `{ state, connected }` where `state` is the latest parsed JSON frame.

**Add the static fallback:**

```javascript
useEffect(() => {
  const ws = new WebSocket(url);
  wsRef.current = ws;

  ws.onopen  = () => setConnected(true);
  ws.onclose = () => { setConnected(false); loadStaticFallback(); };
  ws.onerror = () => { setConnected(false); loadStaticFallback(); };
  ws.onmessage = (e) => {
    try { setState(JSON.parse(e.data)); }
    catch {}
  };
  return () => ws.close();
}, [url]);

async function loadStaticFallback() {
  try {
    const res  = await fetch("/demo_episode.json");   // served from public/
    const data = await res.json();
    // Replay at ~7fps
    let i = 0;
    const timer = setInterval(() => {
      if (i >= data.length) { clearInterval(timer); return; }
      setState(data[i++]);
    }, 150);
    return () => clearInterval(timer);
  } catch {
    console.warn("Static fallback not found — backend must be running");
  }
}
```

Copy `results/demo_episode.json` to `frontend/public/demo_episode.json` so it's served by the React dev server.

---

## Component specifications

### `NetworkGraph.jsx` — D3 force-directed network (implement with D3)

**What to build:** A force-directed graph of 6 nodes (one per host) connected by edges representing network topology. Each node's color reflects its current state.

**Node colors:**
- Normal: `var(--healthy)` (cyan, dim)
- Compromised: `var(--compromised)` (red, pulsing)
- Honeypot active: `var(--honeypot)` (amber)
- Drift alarm: add a dashed border ring

**Implementation:**

```jsx
import { useEffect, useRef } from "react";
import * as d3 from "d3";

const TOPOLOGY = {
  nodes: [
    { id: "User0",       x: 100, y: 150 },
    { id: "User1",       x: 100, y: 250 },
    { id: "User2",       x: 100, y: 350 },
    { id: "Enterprise0", x: 300, y: 200 },
    { id: "Enterprise1", x: 300, y: 300 },
    { id: "Op_Server0",  x: 500, y: 250 },
  ],
  links: [
    { source: "User0", target: "Enterprise0" },
    { source: "User1", target: "Enterprise0" },
    { source: "User2", target: "Enterprise1" },
    { source: "Enterprise0", target: "Op_Server0" },
    { source: "Enterprise1", target: "Op_Server0" },
  ],
};

export default function NetworkGraph({ hosts }) {
  const svgRef = useRef(null);
  
  // Initial render: draw static topology with D3
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    // Draw links as lines
    // Draw nodes as circles with labels
    // Attach host IDs to nodes for update lookup
  }, []);  // run once
  
  // Update: re-color nodes on each frame
  useEffect(() => {
    if (!hosts) return;
    const svg = d3.select(svgRef.current);
    hosts.forEach(h => {
      const color = h.compromised ? "var(--compromised)"
                  : h.honeypot   ? "var(--honeypot)"
                  :                "var(--healthy)";
      svg.select(`#node-${h.id.replace("_", "-")}`)
         .transition().duration(100)
         .attr("fill", color);
    });
  }, [hosts]);  // run on every frame
  
  return (
    <div className="panel-inner">
      <h3 className="panel-title">Network State</h3>
      <p className="panel-label">Heuristic honeypot trigger — not game-theoretic policy</p>
      <svg ref={svgRef} width="600" height="400" />
    </div>
  );
}
```

**The honeypot label is mandatory.** Every time a node turns amber, the label "Heuristic trigger — not signaling game policy" must be visible in the panel. This is the architectural honesty requirement — never present the honeypot activation as the game-theoretic decision.

### `ConvergencePanel.jsx` — hero visual (implement with Recharts)

**This is the most important panel. It must work before the demo.**

**What to build:** A Recharts `LineChart` showing `learned_r` (cyan) converging toward `pbe_r_star` (purple dashed) over training steps. When running live, it updates every time a `convergence` field appears in the WebSocket frame.

```jsx
import { LineChart, Line, XAxis, YAxis, ReferenceLine, Tooltip, ResponsiveContainer } from "recharts";

export default function ConvergencePanel({ data }) {
  // data: { history: [{step, r}], pbe_r_star: number, kappa: number }
  if (!data) return (
    <div className="panel-inner">
      <h3 className="panel-title">Layer 3: RL → PBE Convergence ★</h3>
      <p className="panel-placeholder">Awaiting convergence data…</p>
    </div>
  );
  
  return (
    <div className="panel-inner">
      <h3 className="panel-title">
        Layer 3: RL → PBE Convergence ★ (κ = {data.kappa})
      </h3>
      <p className="panel-subtitle">
        Cyan: learned RL policy · Purple dashed: game-theoretic PBE benchmark
      </p>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data.history}>
          <XAxis dataKey="step" stroke="var(--muted)" tickFormatter={v => `${v/1000}k`} />
          <YAxis domain={[0, 1]} stroke="var(--muted)" />
          <ReferenceLine y={data.pbe_r_star} stroke="var(--pbe-line)"
                         strokeDasharray="6 3" label={{ value: `PBE r*=${data.pbe_r_star.toFixed(3)}`, fill: "var(--pbe-line)" }} />
          <Line type="monotone" dataKey="r" stroke="var(--rl-line)" dot={false} strokeWidth={2} />
          <Tooltip contentStyle={{ background: "var(--surface)", border: "none", color: "var(--text)" }} />
        </LineChart>
      </ResponsiveContainer>
      <p className="panel-note">
        "Purple line: what game theory predicts. Cyan line: what the AI learned from scratch."
      </p>
    </div>
  );
}
```

**If the backend isn't streaming convergence data in real time**, load the pre-generated convergence plot from `results/convergence/convergence_plot.png` as a static image in this panel as a fallback:

```jsx
// Fallback: static image if no live convergence data
if (!data?.history?.length) {
  return (
    <div className="panel-inner">
      <h3 className="panel-title">Layer 3: RL → PBE Convergence ★</h3>
      <img src="/convergence_plot.png" alt="Convergence plot" style={{ width: "100%" }} />
    </div>
  );
}
```

Copy `results/convergence/convergence_plot.png` to `frontend/public/` so it's served correctly.

### `AnomalyPanel.jsx` — Layer 1 time series (implement with Recharts)

Rolling time series of anomaly scores per host. Each host is a separate line colored by current state.

```jsx
// Simple rolling buffer: keep last 60 steps
const [history, setHistory] = useState([]);
useEffect(() => {
  if (!scores) return;
  setHistory(prev => {
    const entry = { step: prev.length, ...scores };  // { step, User0: 0.3, ... }
    return [...prev.slice(-60), entry];
  });
}, [scores]);
```

### `LearningPanel.jsx` — Layer 2 reward curve (implement with Recharts)

Rolling reward history as a line chart. Show a horizontal line at 0 (break-even between compromise costs and detection rewards).

### `DriftPanel.jsx` — Layer 4 centroid scatter (implement with Recharts ScatterChart)

2D scatter plot of centroid positions over time, one trace per host. Color by host name. Add a "drift alarm" marker (X) when `drift_alarm` is True for a host.

---

## CSS — complete `src/styles/index.css`

Add to the existing stylesheet:

```css
:root {
  --healthy:    #22d3ee;
  --compromised:#ef4444;
  --honeypot:   #f59e0b;
  --pbe-line:   #a855f7;
  --rl-line:    #22d3ee;
  --bg:         #0a0e1a;
  --surface:    #111827;
  --muted:      #64748b;
  --text:       #e2e8f0;
}

body { background: var(--bg); color: var(--text); font-family: system-ui, monospace; margin: 0; }

.app-root   { display: flex; flex-direction: column; height: 100vh; }
.app-header { display: flex; align-items: center; gap: 16px; padding: 12px 24px;
              background: var(--surface); border-bottom: 1px solid var(--muted); }
.app-title  { font-size: 1.4rem; font-weight: 700; letter-spacing: 0.1em; color: var(--healthy); }
.app-subtitle { font-size: 0.85rem; color: var(--muted); }
.connection-status.connected    { color: var(--healthy); font-size: 0.8rem; margin-left: auto; }
.connection-status.disconnected { color: var(--compromised); font-size: 0.8rem; margin-left: auto; }

.app-grid {
  display: grid;
  grid-template-columns: 1fr 2fr;
  grid-template-rows: 2fr 1fr;
  grid-template-areas:
    "network hero"
    "anomaly learning drift";  /* bottom: 3 cols */
  gap: 8px;
  padding: 8px;
  flex: 1;
  overflow: hidden;
}

/* Adjust bottom row to 3 equal columns */
.app-grid > :nth-child(3) { grid-column: 1; grid-row: 2; }
.app-grid > :nth-child(4) { grid-column: 2; grid-row: 2; }
.app-grid > :nth-child(5) { grid-column: 3; grid-row: 2; }

.panel          { background: var(--surface); border-radius: 8px; overflow: hidden; }
.panel--hero    { grid-area: hero; }
.panel--network { grid-area: network; }
.panel-inner    { padding: 12px; height: 100%; box-sizing: border-box; }
.panel-title    { font-size: 0.9rem; font-weight: 600; color: var(--text); margin: 0 0 4px; }
.panel-subtitle { font-size: 0.75rem; color: var(--muted); margin: 0 0 8px; }
.panel-label    { font-size: 0.7rem; color: var(--honeypot); margin: 0 0 4px; font-style: italic; }
.panel-note     { font-size: 0.75rem; color: var(--muted); margin: 8px 0 0; }
.panel-placeholder { color: var(--muted); font-size: 0.85rem; }
```
