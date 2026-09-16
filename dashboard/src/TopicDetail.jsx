import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchJSON } from "./api";

export default function TopicDetail() {
  const { id } = useParams();
  const [topic, setTopic] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setTopic(null);
    setError(null);
    fetchJSON(`/api/topics/${id}`)
      .then(setTopic)
      .catch((e) => setError(e.message));
  }, [id]);

  return (
    <div style={{ maxWidth: 700, margin: "0 auto", padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <Link to="/">&larr; Back to overview</Link>

      {error && <p style={{ color: "#c62828" }}>{error}</p>}
      {!topic && !error && <p>Loading...</p>}

      {topic && (
        <>
          <h1 style={{ marginTop: 16 }}>{topic.top_terms.join(", ")}</h1>
          <p style={{ color: "#666" }}>
            {topic.top_condition} &middot; {topic.n_reviews.toLocaleString()} reviews &middot; avg sentiment{" "}
            {topic.avg_sentiment.toFixed(2)}
          </p>
          {topic.is_small_topic && (
            <p style={{ color: "#c62828", fontSize: 14 }}>
              This topic is small — treat as illustrative, not a robust standalone pattern.
            </p>
          )}

          <h3 style={{ marginTop: 24 }}>Example reviews</h3>
          {topic.example_quotes.length === 0 && <p>No examples available for this topic.</p>}
          <div style={{ display: "grid", gap: 12 }}>
            {topic.example_quotes.map((q, i) => (
              <blockquote
                key={i}
                style={{
                  margin: 0,
                  padding: 12,
                  background: "#f7f7f7",
                  borderLeft: "3px solid #ccc",
                  fontStyle: "italic",
                }}
              >
                {q}
              </blockquote>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
