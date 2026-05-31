/**
 * hooks/useWebSocket.js
 *
 * Tries a live WebSocket connection to ws://localhost:8765.
 * On failure (or when socket never connects), falls back to
 * static JSON replay from /demo_episode.json with play/pause/step controls.
 *
 * Returns:
 *   state       — current step data object (or null)
 *   meta        — episode metadata (host_names, thresholds, evasion_matrix, …)
 *   step        — current step index
 *   totalSteps  — total steps in episode
 *   connected   — true if live WebSocket is active
 *   playing     — true if auto-advancing
 *   play()      — start auto-advance
 *   pause()     — stop auto-advance
 *   stepForward()  — advance one step
 *   stepBack()     — go back one step
 *   setStep(n)     — jump to step n
 */
import { useState, useEffect, useRef, useCallback } from "react";

const STEP_INTERVAL_MS = 600;   // ms between auto-advance steps

export default function useWebSocket(url) {
  const [steps,     setSteps]     = useState([]);   // full episode steps array
  const [meta,      setMeta]      = useState(null);
  const [step,      setStepIdx]   = useState(0);
  const [connected, setConnected] = useState(false);
  const [playing,   setPlaying]   = useState(false);

  const wsRef       = useRef(null);
  const timerRef    = useRef(null);
  const stepsRef    = useRef([]);   // mirror for timer callback

  // Keep ref in sync
  useEffect(() => { stepsRef.current = steps; }, [steps]);

  // ------------------------------------------------------------------
  // Static JSON fallback
  // ------------------------------------------------------------------
  const loadStatic = useCallback(() => {
    fetch("/demo_episode.json")
      .then((r) => r.json())
      .then((data) => {
        setMeta(data.meta);
        setSteps(data.steps || []);
        setStepIdx(0);
        console.log("[SOMA] Loaded static episode:", data.steps?.length, "steps");
      })
      .catch((e) => console.warn("[SOMA] Could not load demo_episode.json:", e));
  }, []);

  // ------------------------------------------------------------------
  // WebSocket (try live first)
  // ------------------------------------------------------------------
  useEffect(() => {
    let wsConnected = false;
    let fallbackTimer;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        wsConnected = true;
        setConnected(true);
        clearTimeout(fallbackTimer);
      };

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.steps) {
            // Static export format: full episode in one message
            setMeta(msg.meta);
            setSteps(msg.steps);
          } else if (msg.step !== undefined && !msg.error) {
            // Live stream: individual step frames arriving in real time
            setSteps((prev) => {
              const next = [...prev];
              next[msg.step] = msg;
              return next;
            });
            setStepIdx(msg.step);
          } else if (msg.meta) {
            // Meta-only handshake frame sent at session start
            setMeta(msg.meta);
          }
        } catch { /* ignore */ }
      };

      ws.onclose  = () => { setConnected(false); if (!wsConnected) loadStatic(); };
      ws.onerror  = () => { setConnected(false); };

      // If no connection after 1.5 s, fall back to static
      fallbackTimer = setTimeout(() => {
        if (!wsConnected) {
          ws.close();
          loadStatic();
        }
      }, 1500);

    } catch {
      loadStatic();
    }

    return () => {
      clearTimeout(fallbackTimer);
      wsRef.current?.close();
    };
  }, [url, loadStatic]);

  // ------------------------------------------------------------------
  // Auto-advance timer
  // ------------------------------------------------------------------
  useEffect(() => {
    if (playing && steps.length > 0) {
      timerRef.current = setInterval(() => {
        setStepIdx((prev) => {
          const next = prev + 1;
          if (next >= stepsRef.current.length) {
            setPlaying(false);
            return prev;
          }
          return next;
        });
      }, STEP_INTERVAL_MS);
    }
    return () => clearInterval(timerRef.current);
  }, [playing, steps.length]);

  // ------------------------------------------------------------------
  // Controls
  // ------------------------------------------------------------------
  const play        = useCallback(() => setPlaying(true),  []);
  const pause       = useCallback(() => setPlaying(false), []);
  const stepForward = useCallback(() => {
    setPlaying(false);
    setStepIdx((p) => Math.min(p + 1, stepsRef.current.length - 1));
  }, []);
  const stepBack    = useCallback(() => {
    setPlaying(false);
    setStepIdx((p) => Math.max(p - 1, 0));
  }, []);
  const setStep     = useCallback((n) => {
    setPlaying(false);
    setStepIdx(Math.max(0, Math.min(n, stepsRef.current.length - 1)));
  }, []);

  const state = steps[step] ?? null;

  // Inject all steps into meta so TimelinePanel can draw full history
  const metaWithSteps = meta ? { ...meta, _steps: steps } : null;

  return {
    state,
    meta: metaWithSteps,
    step,
    totalSteps: steps.length,
    connected,
    playing,
    play,
    pause,
    stepForward,
    stepBack,
    setStep,
  };
}
