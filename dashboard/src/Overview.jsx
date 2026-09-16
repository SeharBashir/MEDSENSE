import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchJSON } from "./api";

function sentimentColor(s) {
  if (s > 0.15) return "#2e7d32";
  if (s < -0.15) return "#c62828";
  return "#757575";
}

export default function Overview() {
  const [insights, setInsights] = useState(null);
  const [topics, setTopics] = useState(null);
  const [sort, setSort] = useState("n_reviews");
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchJSON("/api/insights").then((d) => setInsights(d.insights)).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    fetchJSON(`/api/topics?sort=${sort}`)
      .then((d) => setTopics(d.topics))
      .catch((e) => setError(e.message));
  }, [sort]);

  if (error) {
    return <div style={{ padding: 24, color: "#c62828" }}>Error loading data: {error}</div>;
  }

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1>MedSense</h1>
      <p style={{ color: "#555" }}>Patient feedback intelligence — topics and insights discovered from drug reviews.</p>

      <h2>Key Insights</h2>
      {!insights && <p>Loading...</p>}
      <div style={{ display: "grid", gap: 12 }}>
        {insights?.map((ins) => (
          <div key={ins.name} style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <strong>{ins.description}</strong>
              <span style={{ color: sentimentColor(ins.avg_sentiment), fontWeight: 600 }}>
                {ins.avg_sentiment.toFixed(2)}
              </span>
            </div>
            <div style={{ fontSize: 14, color: "#666", marginTop: 4 }}>
              {ins.n_total_reviews.toLocaleString()} reviews
              {ins.example_quotes?.length > 0 && (
                <div style={{ marginTop: 8, fontStyle: "italic", color: "#444" }}>
                  "{ins.example_quotes[0].slice(0, 180)}{ins.example_quotes[0].length > 180 ? "..." : ""}"
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <h2 style={{ marginTop: 32 }}>All Topics</h2>
      <div style={{ marginBottom: 12 }}>
        Sort by:{" "}
        <select value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="n_reviews">Size</option>
          <option value="avg_sentiment">Sentiment</option>
        </select>
      </div>
      {!topics && <p>Loading...</p>}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #ddd" }}>
            <th style={{ padding: 8 }}>Topic</th>
            <th style={{ padding: 8 }}>Condition</th>
            <th style={{ padding: 8 }}>Reviews</th>
            <th style={{ padding: 8 }}>Sentiment</th>
          </tr>
        </thead>
        <tbody>
          {topics?.map((t) => (
            <tr key={t.topic_id} style={{ borderBottom: "1px solid #eee" }}>
              <td style={{ padding: 8 }}>
                <Link to={`/topics/${t.topic_id}`}>{t.top_terms.slice(0, 3).join(", ")}</Link>
                {t.is_small_topic && (
                  <span style={{ fontSize: 11, color: "#c62828", marginLeft: 6 }}>small</span>
                )}
              </td>
              <td style={{ padding: 8, color: "#666" }}>{t.top_condition}</td>
              <td style={{ padding: 8 }}>{t.n_reviews.toLocaleString()}</td>
              <td style={{ padding: 8, color: sentimentColor(t.avg_sentiment) }}>
                {t.avg_sentiment.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
