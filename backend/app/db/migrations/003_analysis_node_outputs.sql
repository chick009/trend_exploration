-- Store structured per-node state snapshots for each analysis run so the
-- frontend can inspect the latest output for every LangGraph step.
ALTER TABLE analysis_runs ADD COLUMN node_outputs_json TEXT;
