import { ImageResponse } from "next/og";

// The link preview for every post that carries this URL. Built as a route rather than a
// static PNG so the claim on the card cannot drift from the claim on the page.
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Brightline — a read-only record of an autonomous options agent";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#101010",
          color: "#fafafa",
          padding: "72px 80px",
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
        }}
      >
        <div style={{ display: "flex", fontSize: 22, letterSpacing: 4, color: "#8a8a8a" }}>
          ALPACA AI TRADING AGENTS · OPTIONS ALPHA
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ display: "flex", fontSize: 116, fontWeight: 700, letterSpacing: -3 }}>
            Brightline
          </div>
          <div style={{ display: "flex", fontSize: 38, color: "#c8c8c8", maxWidth: 900 }}>
            A bright-line rule admits no judgment. Neither does ours.
          </div>
        </div>

        <div
          style={{
            display: "flex",
            gap: 56,
            fontSize: 24,
            color: "#8a8a8a",
            fontFamily: "ui-monospace, SFMono-Regular, monospace",
          }}
        >
          <div style={{ display: "flex" }}>three models scored every cycle</div>
          <div style={{ display: "flex" }}>one may execute</div>
          <div style={{ display: "flex" }}>every refusal on the record</div>
        </div>
      </div>
    ),
    size,
  );
}
