import { useMemo, useState } from "react";

import type { RunStatusResponse, ToolInvocation } from "../api/types";
import { formatDateTime } from "../lib/utils";
import type { GraphWorkflowStep } from "./GraphWorkflowPanel";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, StatusPill } from "./ui";

type Props = {
  step?: GraphWorkflowStep;
  analysisRun?: RunStatusResponse;
};

function getScopedInvocations(nodeId: string, invocations: ToolInvocation[]): ToolInvocation[] {
  switch (nodeId) {
    case "backend_preload":
      return invocations.filter((entry) => entry.node === "sql_dispatcher");
    case "trend_gen_agent":
      return invocations.filter((entry) => entry.node.startsWith("trend_gen_agent:"));
    default:
      return invocations.filter((entry) => entry.node === nodeId);
  }
}

function getNodeOutput(nodeId: string, analysisRun?: RunStatusResponse): unknown {
  if (!analysisRun) {
    return undefined;
  }
  if (analysisRun.node_outputs?.[nodeId] !== undefined) {
    return analysisRun.node_outputs[nodeId];
  }
  if (nodeId === "confidence_gate") {
    const gateLine = analysisRun.execution_trace.find((line) => line.includes("[ConfidenceGate]"));
    return gateLine ? { route: gateLine } : undefined;
  }
  return analysisRun.node_outputs?.[nodeId];
}

type NodeSnapshot = {
  received_state?: unknown;
  emitted_state?: unknown;
  raw_output?: unknown;
};

function normalizeSnapshot(nodeOutput: unknown): NodeSnapshot {
  if (!nodeOutput || typeof nodeOutput !== "object") {
    return {};
  }
  const snapshot = nodeOutput as Record<string, unknown>;
  if ("received_state" in snapshot || "emitted_state" in snapshot || "raw_output" in snapshot) {
    return {
      received_state: snapshot.received_state,
      emitted_state: snapshot.emitted_state,
      raw_output: snapshot.raw_output,
    };
  }
  return {
    emitted_state: snapshot,
    raw_output: snapshot,
  };
}

function formatDuration(durationMs?: number | null): string | null {
  if (durationMs == null || Number.isNaN(durationMs)) {
    return null;
  }
  if (durationMs < 1000) {
    return `${Math.round(durationMs)} ms`;
  }
  return `${(durationMs / 1000).toFixed(2)} s`;
}

function totalDuration(invocations: ToolInvocation[]) {
  return invocations.reduce((sum, entry) => sum + (entry.duration_ms ?? 0), 0);
}

function summarizeScopedLlm(invocations: ToolInvocation[]) {
  return invocations
    .filter((entry) => entry.tool_kind === "llm")
    .reduce(
      (summary, entry) => {
        const metadata = entry.metadata ?? {};
        summary.promptTokens += typeof metadata.prompt_tokens === "number" ? metadata.prompt_tokens : 0;
        summary.completionTokens += typeof metadata.completion_tokens === "number" ? metadata.completion_tokens : 0;
        summary.totalTokens +=
          typeof metadata.total_tokens === "number"
            ? metadata.total_tokens
            : (typeof metadata.prompt_tokens === "number" ? metadata.prompt_tokens : 0) +
              (typeof metadata.completion_tokens === "number" ? metadata.completion_tokens : 0);
        if (typeof metadata.estimated_cost_usd === "number") {
          summary.estimatedCostUsd += metadata.estimated_cost_usd;
          summary.hasKnownCost = true;
        }
        return summary;
      },
      { promptTokens: 0, completionTokens: 0, totalTokens: 0, estimatedCostUsd: 0, hasKnownCost: false },
    );
}

function formatTokenCount(value: number) {
  return value.toLocaleString();
}

function formatUsd(value: number) {
  return `$${value.toFixed(4)}`;
}

function ScopedGuardrailFlags(nodeId: string, output: unknown, runFlags: string[]) {
  if (nodeId === "memory_write") {
    return runFlags.filter((flag) => flag.toLowerCase().includes("trend_exploration"));
  }
  const normalized = normalizeSnapshot(output);
  if (nodeId === "evidence_synthesizer" && normalized.raw_output && typeof normalized.raw_output === "object") {
    const flags = (normalized.raw_output as { guardrail_flags?: string[] }).guardrail_flags;
    return Array.isArray(flags) ? flags : [];
  }
  return [];
}

function CopyBlock({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  };

  return (
    <details className="rounded-2xl border border-white/10 bg-slate-950/50">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
        <span className="text-sm font-medium text-slate-200">{label}</span>
        <Button variant="ghost" size="sm" onClick={onCopy}>
          {copied ? "Copied" : "Copy"}
        </Button>
      </summary>
      <div className="border-t border-white/10 px-4 py-4">
        <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/80 p-4 text-xs leading-6 text-slate-200">
          {value}
        </pre>
      </div>
    </details>
  );
}

function InvocationCard({ invocation, index }: { invocation: ToolInvocation; index: number }) {
  return (
    <details className="rounded-3xl border border-white/10 bg-white/4">
      <summary className="flex cursor-pointer list-none flex-wrap items-start justify-between gap-3 px-4 py-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge tone={invocation.tool_kind === "llm" ? "accent" : invocation.tool_kind === "sql" ? "info" : "success"}>
              {invocation.tool_kind.toUpperCase()}
            </Badge>
            <span className="uppercase tracking-[0.16em] text-slate-500">#{index + 1}</span>
            <code className="inline-code">{invocation.tool}</code>
          </div>
          <div className="text-sm font-semibold text-slate-100">{invocation.title}</div>
          <div className="text-xs uppercase tracking-[0.16em] text-slate-500">{invocation.node}</div>
        </div>
        <div className="flex flex-col items-end gap-1 text-xs text-slate-400">
          <StatusPill status={invocation.status === "success" ? "completed" : invocation.status} />
          {formatDuration(invocation.duration_ms)}
          {invocation.started_at ? <span>{formatDateTime(invocation.started_at)}</span> : null}
        </div>
      </summary>

      <div className="space-y-3 border-t border-white/10 px-4 py-4">
        {invocation.input_summary ? (
          <div className="rounded-2xl border border-white/10 bg-white/3 px-4 py-3 text-sm text-slate-300">
            <span className="text-slate-500">Input summary: </span>
            {invocation.input_summary}
          </div>
        ) : null}

        {invocation.output_summary ? (
          <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-3 text-sm text-emerald-100">
            <span className="text-emerald-300/80">Output summary: </span>
            {invocation.output_summary}
          </div>
        ) : null}

        {invocation.system_prompt ? <CopyBlock label="System prompt" value={invocation.system_prompt} /> : null}
        {invocation.user_prompt ? <CopyBlock label="User prompt" value={invocation.user_prompt} /> : null}
        {invocation.response_text ? <CopyBlock label="Model response" value={invocation.response_text} /> : null}

        {invocation.sql ? (
          <details className="rounded-2xl border border-white/10 bg-slate-950/50">
            <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-200">SQL preview</summary>
            <div className="border-t border-white/10 px-4 py-4">
              <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/80 p-4 text-xs leading-6 text-blue-100">
                {invocation.sql}
              </pre>
            </div>
          </details>
        ) : null}

        {invocation.metadata && Object.keys(invocation.metadata).length > 0 ? (
          <details className="rounded-2xl border border-white/10 bg-slate-950/50">
            <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-200">Metadata</summary>
            <div className="border-t border-white/10 px-4 py-4">
              <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/80 p-4 text-xs leading-6 text-slate-200">
                {JSON.stringify(invocation.metadata, null, 2)}
              </pre>
            </div>
          </details>
        ) : null}

        {invocation.error ? (
          <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {invocation.error}
          </div>
        ) : null}
      </div>
    </details>
  );
}

export function AgentNodeDrawer({ step, analysisRun }: Props) {
  const scopedInvocations = useMemo(() => {
    if (!step || !analysisRun) {
      return [];
    }
    return getScopedInvocations(step.nodeId, analysisRun.tool_invocations ?? []);
  }, [analysisRun, step]);

  const nodeOutput = step ? getNodeOutput(step.nodeId, analysisRun) : undefined;
  const snapshot = normalizeSnapshot(nodeOutput);
  const guardrailFlags = step ? ScopedGuardrailFlags(step.nodeId, nodeOutput, analysisRun?.guardrail_flags ?? []) : [];
  const durationMs = totalDuration(scopedInvocations);
  const llmInvocationCount = scopedInvocations.filter((invocation) => invocation.tool_kind === "llm").length;
  const llmSummary = summarizeScopedLlm(scopedInvocations);

  if (!step) {
    return (
      <Card>
        <CardHeader>
          <Badge tone="accent">Node inspector</Badge>
          <CardTitle>Select a logic-flow node</CardTitle>
          <CardDescription>Pick a node on the left to inspect shared state, prompt handoff, tool calls, and emitted output.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="gap-4 border-b border-white/10 pb-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <Badge tone="accent">Node inspector</Badge>
            <div className="space-y-1">
              <CardTitle>{step.title}</CardTitle>
              <CardDescription>
                Inspect what this layer received in shared state, what prompts it sent, what responses came back, and what it passed forward.
              </CardDescription>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <StatusPill status={step.status === "complete" ? "completed" : step.status === "error" ? "failed" : step.status} />
            <code className="inline-code">{step.nodeId}</code>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <details open className="rounded-2xl border border-white/10 bg-white/3">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-100">Overview</summary>
          <div className="grid gap-3 border-t border-white/10 px-4 py-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3">
              <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Status</div>
              <div className="mt-2 text-sm text-slate-100">{step.status}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3">
              <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Tool calls</div>
              <div className="mt-2 text-sm text-slate-100">{scopedInvocations.length}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3">
              <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Total duration</div>
              <div className="mt-2 text-sm text-slate-100">{formatDuration(durationMs) ?? "n/a"}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3">
              <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Run id</div>
              <div className="mt-2 text-sm text-slate-100">{analysisRun?.id ?? "n/a"}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3">
              <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Prompt exchanges</div>
              <div className="mt-2 text-sm text-slate-100">{llmInvocationCount}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3">
              <div className="text-xs uppercase tracking-[0.16em] text-slate-500">LLM tokens</div>
              <div className="mt-2 text-sm text-slate-100">{formatTokenCount(llmSummary.totalTokens)}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3">
              <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Prompt / completion</div>
              <div className="mt-2 text-sm text-slate-100">
                {formatTokenCount(llmSummary.promptTokens)} / {formatTokenCount(llmSummary.completionTokens)}
              </div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3">
              <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Estimated cost</div>
              <div className="mt-2 text-sm text-slate-100">
                {llmSummary.hasKnownCost ? formatUsd(llmSummary.estimatedCostUsd) : "n/a"}
              </div>
            </div>
          </div>

          {guardrailFlags.length > 0 ? (
            <div className="space-y-2 border-t border-white/10 px-4 py-4">
              {guardrailFlags.map((flag) => (
                <div key={flag} className="rounded-2xl border border-amber-400/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                  {flag}
                </div>
              ))}
            </div>
          ) : null}
        </details>

        <details className="rounded-2xl border border-white/10 bg-white/3">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-100">Shared state received</summary>
          <div className="border-t border-white/10 px-4 py-4">
            {snapshot.received_state !== undefined ? (
              <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/80 p-4 text-xs leading-6 text-slate-200">
                {JSON.stringify(snapshot.received_state, null, 2)}
              </pre>
            ) : (
              <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-sm text-slate-500">
                No received shared-state snapshot captured for this node yet.
              </div>
            )}
          </div>
        </details>

        <details className="rounded-2xl border border-white/10 bg-white/3">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-100">
            Prompt and tool handoff ({scopedInvocations.length})
          </summary>
          <div className="space-y-3 border-t border-white/10 px-4 py-4">
            {scopedInvocations.length > 0 ? (
              scopedInvocations.map((invocation, index) => (
                <InvocationCard key={invocation.id} invocation={invocation} index={index} />
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-sm text-slate-500">
                No structured tool calls captured for this node yet.
              </div>
            )}
          </div>
        </details>

        <details className="rounded-2xl border border-white/10 bg-white/3">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-100">Shared state emitted</summary>
          <div className="border-t border-white/10 px-4 py-4">
            {snapshot.emitted_state !== undefined ? (
              <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/80 p-4 text-xs leading-6 text-slate-200">
                {JSON.stringify(snapshot.emitted_state, null, 2)}
              </pre>
            ) : (
              <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-sm text-slate-500">
                No emitted shared-state snapshot captured for this node yet.
              </div>
            )}
          </div>
        </details>

        <details className="rounded-2xl border border-white/10 bg-white/3">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-100">Raw node snapshot</summary>
          <div className="border-t border-white/10 px-4 py-4">
            {snapshot.raw_output !== undefined ? (
              <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/80 p-4 text-xs leading-6 text-slate-200">
                {JSON.stringify(snapshot.raw_output, null, 2)}
              </pre>
            ) : (
              <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-sm text-slate-500">
                No raw node snapshot captured for this node yet.
              </div>
            )}
          </div>
        </details>
      </CardContent>
    </Card>
  );
}
