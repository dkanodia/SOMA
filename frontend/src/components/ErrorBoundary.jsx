import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.warn("[SOMA] Panel error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          padding: 16,
          color: "#A83D2E",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: 11,
          display: "flex",
          flexDirection: "column",
          gap: 4,
        }}>
          <strong>Panel unavailable</strong>
          <span style={{ color: "#807C76", fontSize: 10 }}>
            {this.state.error.message}
          </span>
        </div>
      );
    }
    return this.props.children;
  }
}
