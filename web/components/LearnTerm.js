"use client";

import { useRef } from "react";

export default function LearnTerm({ slug, ticker, children }) {
  const label = typeof children === "string" ? children : slug;
  const timer = useRef(null);

  function open() {
    window.dispatchEvent(new CustomEvent("finsight:explain", {
      detail: { text: label, ticker: ticker || "" },
    }));
  }

  return (
    <button
      type="button"
      className="learn-term"
      aria-haspopup="dialog"
      aria-label={`${label}. Explain`}
      onClick={open}
      onContextMenu={(event) => {
        event.preventDefault();
        open();
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " " || event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
          event.preventDefault();
          open();
        }
      }}
      onPointerDown={(event) => {
        if (event.pointerType !== "touch") return;
        timer.current = window.setTimeout(open, 550);
      }}
      onPointerUp={() => window.clearTimeout(timer.current)}
      onPointerCancel={() => window.clearTimeout(timer.current)}
      onPointerMove={() => window.clearTimeout(timer.current)}
    >
      {children}
    </button>
  );
}
