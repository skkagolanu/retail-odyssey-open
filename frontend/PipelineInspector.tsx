import type { Reply } from "./types";

export default function PipelineInspector({ reply }: { reply: Reply | null }) {
  const longest = Math.max(
    1,
    ...(reply?.agent_trace.map((event) => event.duration_ms) ?? []),
  );
  return (
    <details className="pipeline-inspector">
      <summary>Behind the reply · agents, handoffs & budgets</summary>
      <div className="pipeline-intro">
        <h2>A coordinated styling workflow</h2>
        <p>
          Intent → optional vision → catalogue retrieval → recommendation →
          conversation → optional image. Agents share this turn’s validated
          context in sequence. Local turns and catalogue mode skip model calls.
        </p>
      </div>
      {reply ? (
        <>
          <ol className="agent-flow">
            {reply.agent_trace.map((event) => (
              <li key={event.sequence}>
                <div>
                  <strong>
                    {event.sequence}. {event.agent}
                  </strong>
                  <span>
                    {event.mode} · {event.status}
                  </span>
                </div>
                <meter
                  min={0}
                  max={longest}
                  value={event.duration_ms}
                  aria-label={`${event.agent} latency`}
                />
                <p>
                  {event.duration_ms.toFixed(1)} ms · handoff:{" "}
                  {event.handoff_keys.join(", ") || "none"}
                </p>
              </li>
            ))}
          </ol>
          <div className="budget-panel">
            <h3>Shared model budget</h3>
            <label>
              Reserved output · {reply.token_budget.reserved_output_tokens} /{" "}
              {reply.token_budget.turn_output_limit}
              <meter
                min={0}
                max={reply.token_budget.turn_output_limit}
                value={reply.token_budget.reserved_output_tokens}
              />
            </label>
            <label>
              Estimated input · {reply.token_budget.reserved_input_tokens} /{" "}
              {reply.token_budget.turn_input_limit}
              <meter
                min={0}
                max={reply.token_budget.turn_input_limit}
                value={reply.token_budget.reserved_input_tokens}
              />
            </label>
            <p>
              Text uses a conservative byte-based estimate; images use a fixed
              reserve. Reserved limits are distinct from actual model-reported
              tokens.
            </p>
            {reply.token_budget.calls.map((call, index) => (
              <p key={index}>
                {call.agent}: {call.usage.prompt_eval_count ?? "unreported"}{" "}
                input / {call.usage.eval_count ?? "unreported"} output tokens ·{" "}
                {call.dropped_history_messages} history messages trimmed
              </p>
            ))}
            <p>
              Trace: <code>{reply.trace_id}</code> · this turn only.
              Server/network time and agent time differ.
            </p>
          </div>
        </>
      ) : (
        <p className="pipeline-intro">
          Send a message to inspect the agents actually invoked, their handoffs
          and timings. No model execution is implied when catalogue mode is
          active.
        </p>
      )}
    </details>
  );
}
