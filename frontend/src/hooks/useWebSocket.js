/**
 * hooks/useWebSocket.js
 *
 * Tries a live WebSocket connection to ws://localhost:8765.
 * Falls back to /demo_episode.json and auto-streams it at a fixed interval.
 *
 * No play/pause — data always flows. Click events in the Timeline to inspect
 * a specific point; the stream continues from there.
 */
import { useState, useEffect, useRef, useCallback } from "react";

const STEP_INTERVAL_MS = 800;

export default function useWebSocket(url) {
  const [steps,     setSteps]     = useState([]);
  const [meta,      setMeta]      = useState(null);
  const [step,      setStepIdx]   = useState(0);
  const [connected, setConnected] = useState(false);

  const wsRef      = useRef(null);
  const timerRef   = useRef(null);
  const stepsRef   = useRef([]);
  const pausedRef  = useRef(false);   // paused only when user clicks timeline

  useEffect(() => { stepsRef.current = steps; }, [steps]);

  // ------------------------------------------------------------------
  // Static fallback — auto-streams from step 0
  // ------------------------------------------------------------------
  const loadStatic = useCallback(() => {
    fetch("/demo_episode.json")
      .then((r) => r.json())
      .then((data) => {
        setMeta(data.meta);
        setSteps(data.steps || []);
        setStepIdx(0);
        pausedRef.current = false;
      })
      .catch((e) => console.warn("[SOMA] Could not load demo_episode.json:", e));
  }, []);

  // ------------------------------------------------------------------
  // WebSocket
  // ------------------------------------------------------------------
  useEffect(() => {
    let wsConnected = false;
    let fallbackTimer;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => { wsConnected = true; setConnected(true); clearTimeout(fallbackTimer); };

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.steps) {
            setMeta(msg.meta); setSteps(msg.steps);
          } else if (msg.step !== undefined && !msg.error) {
            setSteps((prev) => { const n = [...prev]; n[msg.step] = msg; return n; });
            setStepIdx(msg.step);
          } else if (msg.meta) {
            setMeta(msg.meta);
          }
        } catch { /* ignore */ }
      };

      ws.onclose = () => { setConnected(false); if (!wsConnected) loadStatic(); };
      ws.onerror = () => { setConnected(false); };

      fallbackTimer = setTimeout(() => {
        if (!wsConnected) { ws.close(); loadStatic(); }
      }, 1500);
    } catch {
      loadStatic();
    }

    return () => { clearTimeout(fallbackTimer); wsRef.current?.close(); };
  }, [url, loadStatic]);

  // ------------------------------------------------------------------
  // Auto-advance (static mode only — live WS drives step via onmessage)
  // ------------------------------------------------------------------
  useEffect(() => {
    if (connected) return;           // live WS drives itself
    if (stepsRef.current.length === 0) return;

    timerRef.current = setInterval(() => {
      if (pausedRef.current) return;
      setStepIdx((prev) => {
        if (prev + 1 >= stepsRef.current.length) return 0;  // loop
        return prev + 1;
      });
    }, STEP_INTERVAL_MS);

    return () => clearInterval(timerRef.current);
  }, [connected, steps.length]);

  // ------------------------------------------------------------------
  // Timeline click — jump to step, resume after 3 s
  // ------------------------------------------------------------------
  const resumeTimer = useRef(null);
  const setStep = useCallback((n) => {
    pausedRef.current = true;
    setStepIdx(Math.max(0, Math.min(n, stepsRef.current.length - 1)));
    clearTimeout(resumeTimer.current);
    resumeTimer.current = setTimeout(() => { pausedRef.current = false; }, 3000);
  }, []);

  const state = steps[step] ?? null;
  const metaWithSteps = meta ? { ...meta, _steps: steps } : null;

  return { state, meta: metaWithSteps, step, totalSteps: steps.length, connected, setStep };
}
