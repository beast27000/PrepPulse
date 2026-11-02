import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartArtifact, Citation } from "./api";

export default function ChartArtifactView({
  artifact,
  onCitation,
}: {
  artifact: ChartArtifact;
  onCitation: (citation: Citation) => void;
}) {
  const [showTable, setShowTable] = useState(artifact.kind === "table");
  return (
    <div className="artifact-view">
      <p className="artifact-note">{artifact.note}</p>
      <div className="artifact-series-grid">
        {artifact.series.map((series, index) => (
          <section className="artifact-series" key={series.metric_name}>
            <div className="artifact-series-heading">
              <h3>{series.metric_name}</h3>
              <span>
                {series.points.length} recorded values ·{" "}
                {series.points[0]?.unit}
              </span>
            </div>
            {artifact.kind !== "table" && (
              <ResponsiveContainer width="100%" height={230} minWidth={0}>
                <LineChart
                  data={series.points.map((point) => ({
                    ...point,
                    timestamp: new Date(`${point.date}T12:00:00Z`).getTime(),
                  }))}
                  margin={{ top: 15, right: 25, left: 0, bottom: 8 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="var(--chart-grid,#e0e8ec)"
                  />
                  <XAxis
                    dataKey="timestamp"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    scale="time"
                    tickFormatter={(value) =>
                      new Date(value).getUTCFullYear().toString()
                    }
                    tick={{ fontSize: 11 }}
                    minTickGap={25}
                  />
                  <YAxis
                    domain={["auto", "auto"]}
                    tick={{ fontSize: 11 }}
                    width={48}
                  />
                  <Tooltip
                    labelFormatter={(value) =>
                      new Date(Number(value)).toLocaleDateString(undefined, {
                        year: "numeric",
                        month: "short",
                        day: "numeric",
                        timeZone: "UTC",
                      })
                    }
                    formatter={(value) => [
                      `${value} ${series.points[0]?.unit}`,
                      series.metric_name,
                    ]}
                  />
                  <Line
                    type="linear"
                    dataKey="value"
                    name={series.metric_name}
                    stroke={index % 2 ? "#8b6fbe" : "#288c88"}
                    strokeWidth={2.5}
                    connectNulls={false}
                    isAnimationActive={false}
                    activeDot={false}
                    dot={(props: any) => (
                      <circle
                        key={`${props.payload.date}-${props.index}`}
                        cx={props.cx}
                        cy={props.cy}
                        r={5}
                        fill={index % 2 ? "#8b6fbe" : "#288c88"}
                        tabIndex={0}
                        role="button"
                        style={{ cursor: "pointer" }}
                        aria-label={`${series.metric_name} ${props.payload.value} on ${props.payload.date}; view source`}
                        onClick={(event) => {
                          event.stopPropagation();
                          onCitation(props.payload.citation);
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter")
                            onCitation(props.payload.citation);
                        }}
                      />
                    )}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
            {(showTable || artifact.kind === "table") && (
              <div className="reply-table">
                <table>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Recorded value</th>
                      <th>Evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {series.points.map((point) => (
                      <tr key={`${point.date}-${point.citation.document_id}`}>
                        <td>{point.date}</td>
                        <td>
                          <strong>
                            {point.value} {point.unit}
                          </strong>
                        </td>
                        <td>
                          <button
                            className="inline-source"
                            onClick={() => onCitation(point.citation)}
                          >
                            View source ↗
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ))}
      </div>
      {artifact.kind !== "table" && artifact.series.length > 0 && (
        <button
          className="text-button"
          onClick={() => setShowTable(!showTable)}
        >
          {showTable ? "Hide data table" : "Show source data table"}
        </button>
      )}
      {artifact.events.length > 0 && (
        <div className="artifact-timeline">
          {artifact.events.map((event, index) => (
            <button
              key={`${event.date}-${index}`}
              onClick={() => onCitation(event.citation)}
            >
              <time>{event.date}</time>
              <span>
                <strong>{event.title}</strong>
                <small>{event.text}</small>
              </span>
              <span className="timeline-source">Source ↗</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
