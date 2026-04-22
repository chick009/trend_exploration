import { useEffect, useMemo, useRef, useState } from "react";

import { useTrendWorkbench } from "../hooks/useTrendWorkbench";
import { AppHeader } from "./AppHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger, useToast } from "./ui";
import { DataExtractionTab } from "../pages/tabs/DataExtractionTab";
import { ExecutionLogTab } from "../pages/tabs/ExecutionLogTab";
import { LangGraphAgentTab } from "../pages/tabs/LangGraphAgentTab";
import { SqlDatabaseTab } from "../pages/tabs/SqlDatabaseTab";
import { TrendsTab } from "../pages/tabs/TrendsTab";

const tabValues = ["trends", "extraction", "sql", "agent", "execution_log"] as const;
type TabValue = (typeof tabValues)[number];

function getHashTab(): TabValue {
  if (typeof window === "undefined") {
    return "trends";
  }
  const value = window.location.hash.replace(/^#/, "");
  return tabValues.includes(value as TabValue) ? (value as TabValue) : "trends";
}

export function AppShell() {
  const [activeTab, setActiveTab] = useState<TabValue>(getHashTab);
  const workbench = useTrendWorkbench();
  const { pushToast } = useToast();

  const lastIngestionToastRef = useRef<string | null>(null);
  const lastAnalysisToastRef = useRef<string | null>(null);
  const lastErrorToastRef = useRef<string | null>(null);

  useEffect(() => {
    const onHashChange = () => setActiveTab(getHashTab());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (window.location.hash !== `#${activeTab}`) {
      window.history.replaceState(null, "", `#${activeTab}`);
    }
  }, [activeTab]);

  useEffect(() => {
    const runId = workbench.mutations.createIngestionMutation.data?.id;
    if (runId && lastIngestionToastRef.current !== runId) {
      lastIngestionToastRef.current = runId;
      pushToast({
        tone: "success",
        title: "Extraction started",
        description: `Batch ${workbench.mutations.createIngestionMutation.data?.source_batch_id ?? runId} queued successfully.`,
      });
    }
  }, [pushToast, workbench.mutations.createIngestionMutation.data]);

  useEffect(() => {
    const runId = workbench.runState.analysisStartRunId;
    if (runId && lastAnalysisToastRef.current !== runId) {
      lastAnalysisToastRef.current = runId;
      pushToast({
        tone: "success",
        title: "LangGraph run started",
        description: `Analysis run ${runId} is streaming live from the backend.`,
      });
    }
  }, [pushToast, workbench.runState.analysisStartRunId]);

  useEffect(() => {
    const errorMessage =
      (workbench.mutations.createIngestionMutation.error as Error | null)?.message ??
      workbench.runState.runErrorMessage ??
      null;
    if (errorMessage && lastErrorToastRef.current !== errorMessage) {
      lastErrorToastRef.current = errorMessage;
      pushToast({
        tone: "danger",
        title: "Run failed",
        description: errorMessage,
      });
    }
  }, [
    pushToast,
    workbench.mutations.createIngestionMutation.error,
    workbench.runState.runErrorMessage,
  ]);

  const sourceHealth = workbench.queries.sourceHealthQuery.data?.sources ?? [];
  const tabLabels = useMemo(
    () => [
      { value: "trends" as const, label: "Trends", hint: "Saved reports from the database—filter and browse." },
      { value: "extraction" as const, label: "Data Extraction", hint: "Ingest signals and approve keywords before analysis." },
      { value: "sql" as const, label: "SQL Database", hint: "Inspect raw rows in the local warehouse." },
      { value: "agent" as const, label: "LangGraph Agent", hint: "Stream a multi-step run with tools and traces." },
      { value: "execution_log" as const, label: "Execution log", hint: "Extraction and agent run history, errors, and detailed traces." },
    ],
    [],
  );

  return (
    <div className="min-h-screen">
      <div className="mx-auto flex max-w-[1680px] flex-col gap-4 px-3 py-3 md:px-5 md:py-4">
        <AppHeader
          sourceHealth={sourceHealth}
          ingestionStatus={workbench.queries.ingestionQuery.data?.status}
          analysisStatus={workbench.runState.analysisRun?.status}
        />

        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as TabValue)} className="space-y-4">
          <div className="sticky top-3 z-20 space-y-1.5">
            <TabsList className="backdrop-blur-xl">
              {tabLabels.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value} title={tab.hint}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>
            <p className="hidden px-1 text-[11px] text-slate-500 md:block">
              {tabLabels.find((t) => t.value === activeTab)?.hint}
            </p>
          </div>

          <TabsContent value="trends">
            <TrendsTab workbench={workbench} />
          </TabsContent>
          <TabsContent value="extraction">
            <DataExtractionTab workbench={workbench} />
          </TabsContent>
          <TabsContent value="sql">
            <SqlDatabaseTab />
          </TabsContent>
          <TabsContent value="agent">
            <LangGraphAgentTab workbench={workbench} />
          </TabsContent>
          <TabsContent value="execution_log">
            <ExecutionLogTab workbench={workbench} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
