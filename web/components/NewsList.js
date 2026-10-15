function publishedLabel(value) {
  if (!value) return "Time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function tickerLabel(tickers) {
  if (!tickers?.length) return "";
  const shown = tickers.slice(0, 4);
  const extra = tickers.length - shown.length;
  return extra > 0 ? `${shown.join(", ")} +${extra}` : shown.join(", ");
}

export default function NewsList({ items, provider }) {
  if (!items?.length) return null;
  return (
    <div className="news-grid">
      {items.map((item) => (
        <article className={item.image_url ? "news-card" : "news-card no-photo"} key={`${item.url}-${item.headline}`}>
          {item.image_url ? <img src={item.image_url} alt="" /> : <div className="news-photo-fallback" aria-hidden="true">No photo</div>}
          <div className="news-copy">
            <p className="eyebrow">{item.source}{item.sentiment ? ` · ${item.sentiment}` : ""}</p>
            <h3>{item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.headline}</a> : item.headline}</h3>
            {item.summary ? <p>{item.summary}</p> : null}
            <p className="muted">{[tickerLabel(item.tickers), item.provider || provider, publishedLabel(item.published_at)].filter(Boolean).join(" · ")}</p>
          </div>
        </article>
      ))}
    </div>
  );
}
