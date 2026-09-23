// Adapted from Ravi Katiyar's Stats Card, retrieved through 21st MCP.
// https://21st.dev/@ravikatiyar162/components/stats-card-1
// JSX/CSS adaptation: source metric layout; factual context replaces demo trends.
export function StatsCard({title,value,icon,description,accent=false}) {
  return <section className={`metric-card ${accent?'metric-card-accent':''}`}>
    <header><h3>{title}</h3><span aria-hidden="true">{icon}</span></header>
    <div className="metric-card-value">{value}</div>
    <p>{description}</p>
  </section>;
}
