import { AlertTriangle, CheckCircle, XCircle } from "lucide-react";
import type { ConversationAnalysis } from "@/lib/types";

function ScoreRing({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - score);
  return (
    <div className="relative h-20 w-20">
      <svg className="h-20 w-20 -rotate-90" viewBox="0 0 72 72">
        <circle
          cx="36" cy="36" r={radius}
          fill="none" strokeWidth="6" className="stroke-surface-raised"
        />
        <circle
          cx="36" cy="36" r={radius}
          fill="none" strokeWidth="6" strokeLinecap="round"
          className="stroke-accent-light transition-all"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-lg font-semibold text-text-primary">
        {pct}%
      </span>
    </div>
  );
}

export default function AnalysisPanel({ analysis }: { analysis: ConversationAnalysis }) {
  const comment = analysis.participation_recommendation === "COMMENT";

  return (
    <div className="rounded-xl border border-border bg-surface p-6">
      <h2 className="text-lg font-medium text-text-primary">AI Analysis</h2>

      <div className="mt-4 inline-block rounded-full bg-accent/20 px-3 py-1 text-sm text-accent-light">
        {analysis.central_topic}
      </div>

      <div className="mt-4 flex items-center gap-6">
        <div
          className={`flex items-center gap-2 text-sm font-semibold ${comment ? "text-success" : "text-danger"}`}
        >
          {comment ? (
            <CheckCircle className="h-5 w-5" />
          ) : (
            <XCircle className="h-5 w-5" />
          )}
          {comment ? "COMMENT" : "DO NOT COMMENT"}
        </div>
        <ScoreRing score={analysis.relevance_score} />
      </div>
      <p className="mt-2 text-sm text-text-secondary">
        {analysis.recommendation_reason}
      </p>

      {analysis.key_tensions.length > 0 && (
        <div className="mt-5">
          <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">
            Key Tensions
          </h3>
          <ul className="mt-2 list-disc pl-5 text-sm text-text-primary space-y-1">
            {analysis.key_tensions.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </div>
      )}

      {analysis.viewpoints_represented.length > 0 && (
        <div className="mt-5">
          <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide">
            Viewpoints Represented
          </h3>
          <ul className="mt-2 list-disc pl-5 text-sm text-text-primary space-y-1">
            {analysis.viewpoints_represented.map((v, i) => (
              <li key={i}>{v}</li>
            ))}
          </ul>
        </div>
      )}

      {analysis.emotional_sensitivities && (
        <div className="mt-5 flex gap-2 rounded-lg bg-warning/10 p-3">
          <AlertTriangle className="h-4 w-4 shrink-0 text-warning mt-0.5" />
          <p className="text-sm text-text-primary">
            {analysis.emotional_sensitivities}
          </p>
        </div>
      )}

      {analysis.value_reasoning && (
        <blockquote className="mt-5 border-l-2 border-border-bright pl-4 text-sm italic text-text-secondary">
          {analysis.value_reasoning}
        </blockquote>
      )}
    </div>
  );
}
