-- Store per-run structured tool invocations (SQL queries against the internal
-- database, LLM calls, and memory ops) so the frontend can replay a completed
-- analysis run's tool-use timeline without waiting on the live stream.
ALTER TABLE analysis_runs ADD COLUMN tool_invocations_json TEXT;
