/**
 * hooks/useWebSocket.js
 * Connects to SOMA demo server. Falls back to static JSON on failure.
 * TODO: implement static JSON fallback (pre-record with scripts/demo.py --static)
 */
import { useState, useEffect, useRef } from "react";

export default function useWebSocket(url) {
  const [state,     setState]     = useState(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);

  useEffect(() => {
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen  = ()  => setConnected(true);
    ws.onclose = ()  => setConnected(false);
    ws.onerror = ()  => setConnected(false);
    ws.onmessage = (e) => {
      try { setState(JSON.parse(e.data)); }
      catch { /* ignore malformed frames */ }
    };

    return () => ws.close();
  }, [url]);

  return { state, connected };
}
