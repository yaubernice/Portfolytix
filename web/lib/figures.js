function significantCount(unsigned) {
  const [whole, fraction] = unsigned.split(".");
  if (fraction != null) {
    return `${whole}${fraction}`.replace(/^0+/, "").length;
  }
  return whole.replace(/^0+/, "").replace(/0+$/, "").length || 1;
}

export const SHORT_RETURN_SAMPLE = 21;

export function volatilityNote(analytics) {
  if (analytics?.volatility == null) return "Needs at least two daily returns.";
  return shortSampleNote(analytics.observation_count, "Annualized from stored daily returns.", true);
}

export function sharpeNote(analytics) {
  if (analytics?.sharpe_ratio == null) return "Needs at least two daily returns.";
  return shortSampleNote(analytics.observation_count, "From stored daily returns.", false);
}

function shortSampleNote(count, ready, annualized) {
  const n = Number(count);
  if (!Number.isFinite(n) || n <= 0 || n >= SHORT_RETURN_SAMPLE) return ready;
  const noun = n === 1 ? "return" : "returns";
  const lead = annualized ? "Annualized from" : "From";
  const scale = annualized ? " A short sample can make this number very large." : "";
  return `${lead} ${n} stored daily ${noun}.${scale} It is not a long-run risk figure.`;
}

export function roundFigures(text, digits = 4, final = true) {
  if (text == null || text === "") return text ?? "";
  const source = String(text);
  return source.replace(/-?\$?\d[\d,]*(?:\.\d+)?%?/g, (token, offset) => {
    if (!final && offset + token.length >= source.length) return token;
    const percent = token.endsWith("%");
    const dollar = token.includes("$");
    const negative = token.startsWith("-");
    const unsigned = token.replace(/[^0-9.]/g, "");
    if (!unsigned || unsigned === "." || significantCount(unsigned) <= digits) return token;
    const value = Number(unsigned);
    if (!Number.isFinite(value) || value === 0) return token;
    const rounded = Number((negative ? -value : value).toPrecision(digits));
    const formatted = Math.abs(rounded).toLocaleString("en-US", {
      maximumSignificantDigits: digits,
      useGrouping: dollar || Math.abs(rounded) >= 10000,
    });
    return `${rounded < 0 ? "-" : ""}${dollar ? "$" : ""}${formatted}${percent ? "%" : ""}`;
  });
}
