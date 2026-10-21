"use client";

import { useEffect, useState } from "react";

export const ASK_PHASES = [
  "Reading the portfolio evidence…",
  "Estimating the figures…",
  "Writing the answer…",
  "Finalizing the result…",
];

export const NEWS_PHASES = [
  "Reading the story…",
  "Drafting the summary…",
  "Finalizing the result…",
];

export const EXPLAIN_PHASES = [
  "Looking up the term…",
  "Checking this portfolio…",
  "Writing the explanation…",
];

export const SCREEN_PHASES = [
  "Reading the request…",
  "Turning it into filters…",
  "Running the screen…",
];

export default function GeneratingStatus({ phases }) {
  const [index, setIndex] = useState(0);
  const lines = phases.length ? phases : ["Working…"];

  useEffect(() => {
    setIndex(0);
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (media.matches || lines.length < 2) return undefined;
    const timer = setInterval(() => {
      setIndex((current) => (current + 1) % lines.length);
    }, 1600);
    return () => clearInterval(timer);
  }, [lines]);

  return (
    <p className="generating" role="status" aria-live="polite">
      <span className="generating-mark" aria-hidden="true" />
      <span>{lines[index]}</span>
    </p>
  );
}
