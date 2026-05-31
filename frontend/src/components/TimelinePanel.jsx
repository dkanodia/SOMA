/**
 * TimelinePanel.jsx
 *
 * Full-width threat timeline: anomaly score + memory drift per host over time.
 * Recharts ComposedChart with:
 *   - Gray reference area marking the attack window
 *   - Global innate anomaly score (cyan line)
 *   - Memory drift for each host (one line each, dimmed)
 *   - Red reference line for innate threshold
 *   - Click on chart → jump to that step
 */

import React, { useMemo } from "react";
import {
  ComposedChart, Line, Area, ReferenceLine, ReferenceArea,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";

const HOST_COLORS = {
  User0:       "#3A7A58",
  User1:       "#5F8D6F",
  User2:       "#8BA778",
  Enterprise0: "#6452A0",
  Enterprise1: "#8071B8",
  Op_Server0:  "#A83D2E",
};

const FEATURE_NAMES = ["activity","compromised","sessions","processes","network_pos"];

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#171715", border: "1px solid #262624",
      padding: "6px 10px", fontSize: 10, lineHeight: 1.6,
    }}>
      <div style={{ color: "#807C76" }}>Step {label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {typeof p.value === "number" ? p.value.toFixed(3) : p.value}
        </div>
      ))}
    </div>
  );
}

export default function TimelinePanel({ state, meta, currentStep, onStepClick }) {
  // Build timeline data from ALL steps stored in meta (we don't have all steps here).
  // Instead we use a sliding window approach: the component shows a "ghost" line
  // from the current step's obs only.
  //
  // For full timeline we need the parent to pass all steps, but to keep the API simple
  // we accept meta.steps if present (injected by App from the full episode).
  // Fallback: show just current step as a single point.

  const allSteps = meta?._steps ?? [];   // injected by App.jsx if available

  // Compute max anomaly score and drift distances from raw payload fields.
  // Raw payload: anomaly_scores={host:float}, centroid_pos={host:[x,y]|null}
  function stepToChart(s) {
    const anomalyScores = s.anomaly_scores ?? s.anomaly_score != null ? {} : {};
    // Support both enriched (anomaly_score float) and raw (anomaly_scores dict)
    const maxAnomaly = s.anomaly_score != null
      ? s.anomaly_score
      : Math.max(0, ...Object.values(s.anomaly_scores ?? {}));

    const driftScores = {};
    if (s.drift_scores) {
      Object.assign(driftScores, s.drift_scores);
    } else {
      for (const [h, pos] of Object.entries(s.centroid_pos ?? {})) {
        driftScores[h] = pos ? Math.sqrt(pos[0] ** 2 + pos[1] ** 2) : 0;
      }
    }

    return {
      step:      s.step ?? 0,
      anomaly:   maxAnomaly,
      is_attack: s.is_attack ? 1 : 0,
      innate:    s.innate_fired ? 1 : 0,
      ...Object.fromEntries(Object.entries(driftScores).map(([h, v]) => [`drift_${h}`, v])),
    };
  }

  const chartData = useMemo(() => {
    if (allSteps.length) return allSteps.map(stepToChart);
    if (state) return [stepToChart(state)];
    return [];
  }, [allSteps, state]);

  // Derive attack window: first step where innate_fired=true
  const attackStart = useMemo(() => {
    if (meta?.attack_start != null) return meta.attack_start;
    const idx = allSteps.findIndex((s) => s.innate_fired || s.is_attack);
    return idx >= 0 ? allSteps[idx].step : null;
  }, [allSteps, meta]);

  const innateThresh = meta?.innate_threshold ?? 0.5;
  const memThresh    = meta?.memory_threshold  ?? 1.0;
  const hostNames    = meta?.host_names ?? Object.keys(HOST_COLORS);

  function handleClick(data) {
    if (data?.activePayload?.[0] && onStepClick) {
      onStepClick(data.activeLabel);
    }
  }

  return (
    <div className="panel-inner">
      <div className="panel-header">
        <span className="panel-title">Threat timeline — anomaly &amp; memory drift</span>
        <span className="panel-tag">
          {attackStart != null ? `Attack onset: step ${attackStart}` : "No attack detected"}
        </span>
      </div>
      <div className="panel-body panel-body--flush">
        {chartData.length === 0 ? (
          <p className="panel-placeholder">Waiting for episode data…</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 6, right: 48, bottom: 4, left: 0 }}
              onClick={handleClick} style={{ cursor: "crosshair" }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1A1A18" />
              <XAxis dataKey="step" stroke="#262624" tick={{ fill: "#807C76", fontSize: 9 }}
                label={{ value: "step", position: "insideBottomRight", offset: -4, fill: "#807C76", fontSize: 9 }} />
              <YAxis stroke="#262624" tick={{ fill: "#807C76", fontSize: 9 }} width={28} />
              <Tooltip content={<CustomTooltip />} />
              <Legend iconSize={8}
                wrapperStyle={{ fontSize: 9, color: "#807C76", fontFamily: "'IBM Plex Mono',monospace", paddingTop: 2 }} />

              {/* Attack window shading */}
              {attackStart != null && (
                <ReferenceArea
                  x1={attackStart} x2={chartData[chartData.length - 1]?.step}
                  fill="#A83D2E" fillOpacity={0.07}
                  label={{ value: "attack", position: "insideTopLeft", fill: "#A83D2E66", fontSize: 8 }}
                />
              )}

              {/* Innate threshold */}
              <ReferenceLine y={innateThresh} stroke="#C49A3088" strokeDasharray="4 2"
                label={{ value: `inn θ`, position: "right", fill: "#C49A30", fontSize: 8 }} />

              {/* Memory threshold */}
              <ReferenceLine y={memThresh} stroke="#6452A088" strokeDasharray="4 2"
                label={{ value: `mem θ`, position: "right", fill: "#6452A0", fontSize: 8 }} />

              {/* Current step marker */}
              {currentStep != null && (
                <ReferenceLine x={currentStep} stroke="#C49A30" strokeWidth={1.5} strokeDasharray="4 2" />
              )}

              {/* Innate anomaly score — primary line */}
              <Line type="monotone" dataKey="anomaly" name="Innate anomaly"
                stroke="#C49A30" strokeWidth={2} dot={false} isAnimationActive={false} />

              {/* Per-host memory drift */}
              {hostNames.map((h) => (
                <Line key={h} type="monotone" dataKey={`drift_${h}`} name={h}
                  stroke={HOST_COLORS[h] ?? "#807C76"} strokeWidth={1.2}
                  strokeOpacity={0.6} dot={false} isAnimationActive={false} />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
