/**
 * hooks/useWebSocket.js
 *
 * Live demo WebSocket hook — connects to ws://localhost:8765/dashboard
 * and routes the SOMA live-demo message protocol.
 *
 * Offline fallback: after MAX_RETRIES failed connections, fetches
 * /demo_episode.json and replays it at REPLAY_FPS, driving the same
 * state machine as the live backend.
 *
 * State exposed:
 *   connected          bool
 *   replayMode         bool  — true when replaying offline episode
 *   somaState          "CLEAN"|"EMAIL_RECEIVED"|"INFECTED"|"ISOLATING"|"CONTAINED"|"PURGED"
 *   emailNotification  null | {from, subject}
 *   nodes              array of 6 {id, cpu, processes, anomaly_score, status}
 *   honeypotMetrics    null | {cpu, processes, exfil_attempts, lan_scans}
 *   sendMessage        (obj) => void
 */
import { useState, useEffect, useRef, useCallback } from "react";

const RECONNECT_DELAY_MS = 3000;
const MAX_RETRIES        = 3;
const REPLAY_FPS         = 7;
const REPLAY_INTERVAL_MS = Math.round(1000 / REPLAY_FPS); // ~143ms

// ---------------------------------------------------------------------------
// Offline replay helpers
// ---------------------------------------------------------------------------

// Scripted state machine thresholds (in episode step counts within one cycle)
const REPLAY_STATES = {
  EMAIL_AT:     8,   // step at which fake email arrives
  INFECTED_AT:  20,  // step at which INFECTED triggers (auto-advance from EMAIL)
  ISOLATING_AT: 38,  // step at which ISOLATING triggers
  CONTAINED_AT: 40,  // step at which CONTAINED triggers
  PURGED_AT:    55,  // step at which PURGED triggers
  CYCLE_LEN:    65,  // total steps per replay cycle before looping
};

function _replayStateAt(cycleStep) {
  const s = REPLAY_STATES;
  if (cycleStep < s.EMAIL_AT)     return "CLEAN";
  if (cycleStep < s.INFECTED_AT)  return "EMAIL_RECEIVED";
  if (cycleStep < s.ISOLATING_AT) return "INFECTED";
  if (cycleStep < s.CONTAINED_AT) return "ISOLATING";
  if (cycleStep < s.PURGED_AT)    return "CONTAINED";
  return "PURGED";
}

function _buildReplayNodes(episodeStep, cycleStep) {
  const hostNames = ["User0", "User1", "User2", "Enterprise0", "Enterprise1", "Op_Server0"];
  const isInfected = cycleStep >= REPLAY_STATES.INFECTED_AT &&
                     cycleStep <  REPLAY_STATES.PURGED_AT;
  const rawScores = episodeStep?.anomaly_scores ?? {};

  return hostNames.map((name) => {
    let cpu, processes, anomaly_score;

    if (name === "User0" && isInfected) {
      cpu           = 0.88 + (Math.random() * 0.08);
      processes     = 350  + Math.floor(Math.random() * 60);
      anomaly_score = 0.82 + (Math.random() * 0.12);
    } else {
      const raw = rawScores[name] ?? 0;
      cpu           = Math.max(0.03, 0.05 + raw * 0.3 + Math.random() * 0.04);
      processes     = 40   + Math.floor(Math.random() * 40);
      anomaly_score = Math.min(0.45, 0.04 + raw * 2.5 + Math.random() * 0.02);
    }

    const status = anomaly_score > 0.75 ? "red"
                 : anomaly_score > 0.5  ? "yellow"
                 : "green";

    return {
      id:            name,
      cpu:           Math.round(cpu * 1000) / 1000,
      processes,
      anomaly_score: Math.round(anomaly_score * 1000) / 1000,
      status,
    };
  });
}

function _buildHoneypotMetrics() {
  return {
    cpu:            0.55 + Math.random() * 0.25,
    processes:      12   + Math.floor(Math.random() * 8),
    exfil_attempts: 3    + Math.floor(Math.random() * 5),
    lan_scans:      7    + Math.floor(Math.random() * 6),
  };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export default function useWebSocket(url) {
  const [connected,          setConnected]          = useState(false);
  const [replayMode,         setReplayMode]         = useState(false);
  const [somaState,          setSomaState]          = useState("CLEAN");
  const [emailNotification,  setEmailNotification]  = useState(null);
  const [nodes,              setNodes]              = useState([]);
  const [honeypotMetrics,    setHoneypotMetrics]    = useState(null);
  const [detectionSecs,      setDetectionSecs]      = useState(0);
  const [lateralMovements,   setLateralMovements]   = useState([]);

  const wsRef          = useRef(null);
  const reconnectRef   = useRef(null);
  const replayRef      = useRef(null);
  const mountedRef     = useRef(true);
  const retryCountRef  = useRef(0);
  const infectedAtRef  = useRef(0);

  // ── Offline replay ────────────────────────────────────────────────────────

  const startOfflineReplay = useCallback(async () => {
    if (!mountedRef.current) return;
    let episode;
    try {
      const res = await fetch("/demo_episode.json");
      episode = await res.json();
    } catch {
      // If we can't load the episode, just keep showing "Connecting..."
      return;
    }
    if (!mountedRef.current) return;

    setReplayMode(true);
    setConnected(false);

    const steps = episode.steps ?? [];
    let globalStep = 0;
    let prevCycleState = "CLEAN";

    replayRef.current = setInterval(() => {
      if (!mountedRef.current) return;

      const cycleStep    = globalStep % REPLAY_STATES.CYCLE_LEN;
      const episodeIdx   = globalStep % steps.length;
      const episodeStep  = steps[episodeIdx];
      const newState     = _replayStateAt(cycleStep);

      // Emit state transitions
      if (newState !== prevCycleState) {
        setSomaState(newState);

        if (newState === "EMAIL_RECEIVED") {
          setEmailNotification({ from: "attacker@example.com", subject: "SOMA security patch required" });
        }
        if (newState === "INFECTED") {
          infectedAtRef.current = Date.now();
        }
        if (newState === "ISOLATING") {
          const secs = Math.round((Date.now() - infectedAtRef.current) / 1000);
          setDetectionSecs(secs);
        }
        if (newState === "CONTAINED") {
          // keep honeypot metrics updating
        }
        if (newState === "PURGED") {
          setHoneypotMetrics(null);
        }
        if (newState === "CLEAN" && cycleStep === 0 && globalStep > 0) {
          // cycle reset
          setEmailNotification(null);
          setNodes([]);
          setDetectionSecs(0);
        }

        prevCycleState = newState;
      }

      // Emit node_metrics every step
      setNodes(_buildReplayNodes(episodeStep, cycleStep));

      // Update honeypot metrics during CONTAINED
      if (newState === "CONTAINED" || newState === "ISOLATING") {
        setHoneypotMetrics(_buildHoneypotMetrics());
      }

      globalStep++;
    }, REPLAY_INTERVAL_MS);
  }, []);

  const stopOfflineReplay = useCallback(() => {
    if (replayRef.current) {
      clearInterval(replayRef.current);
      replayRef.current = null;
    }
    setReplayMode(false);
  }, []);

  // ── Live WebSocket ─────────────────────────────────────────────────────────

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const wsUrl = url.replace(/\/?$/, "") + "/dashboard";
    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch {
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return; }
      console.log("[SOMA] Dashboard connected");
      retryCountRef.current = 0;
      stopOfflineReplay();
      setConnected(true);
    };

    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }

      switch (msg.type) {
        case "email_notification":
          setEmailNotification({ from: msg.from, subject: msg.subject });
          break;
        case "node_metrics":
          setNodes(msg.nodes ?? []);
          break;
        case "state_change":
          setSomaState(msg.state);
          if (msg.state === "ISOLATING" && msg.detection_secs) {
            setDetectionSecs(msg.detection_secs);
          }
          break;
        case "honeypot_active":
          setHoneypotMetrics(msg.metrics ?? null);
          break;
        case "lateral_movement":
          setLateralMovements(prev => [
            { ...msg, ts: Date.now() },
            ...prev.slice(0, 9),
          ]);
          break;
        case "purge_complete":
          setHoneypotMetrics(null);
          setSomaState("PURGED");
          break;
        case "demo_reset":
          setSomaState("CLEAN");
          setEmailNotification(null);
          setNodes([]);
          setHoneypotMetrics(null);
          setDetectionSecs(0);
          setLateralMovements([]);
          break;
        default:
          break;
      }
    };

    ws.onclose = () => {
      setConnected(false);
      if (!mountedRef.current) return;
      retryCountRef.current += 1;
      if (retryCountRef.current >= MAX_RETRIES) {
        startOfflineReplay();
      } else {
        reconnectRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };

    ws.onerror = () => {
      setConnected(false);
    };
  }, [url, startOfflineReplay, stopOfflineReplay]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectRef.current);
      clearInterval(replayRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((obj) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(obj));
    }
  }, []);

  return {
    connected,
    replayMode,
    somaState,
    emailNotification,
    nodes,
    honeypotMetrics,
    detectionSecs,
    lateralMovements,
    sendMessage,
  };
}
