import { useEffect, useMemo, useRef, useState } from "react";

import { useTrendWorkbench } from "../hooks/useTrendWorkbench";
import { AppHeader } from "./AppHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger, useToast } from "./ui";
import { DataExtractionTab } from "../pages/tabs/DataExtractionTab";
import { LangGraphAgentTab } from "../pages/tabs/LangGraphAgentTab";
import { SqlDatabaseTab } from "../pages/tabs/SqlDatabaseTab";
import { TrendsTab } from "../pages/tabs/TrendsTab";

const tabValues = ["trends", "extraction", "sql", "agent"] as const;
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
    const runId = workbench.mutations.createAnalysisMutation.data?.id;
    if (runId && lastAnalysisToastRef.current !== runId) {
      lastAnalysisToastRef.current = runId;
      pushToast({
        tone: "success",
        title: "LangGraph run started",
        description: `Analysis run ${runId} has been queued.`,
      });
    }
  }, [pushToast, workbench.mutations.createAnalysisMutation.data]);

  useEffect(() => {
    const errorMessage =
      (workbench.mutations.createIngestionMutation.error as Error | null)?.message ??
      (workbench.mutations.createAnalysisMutation.error as Error | null)?.message ??
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
    workbench.mutations.createAnalysisMutation.error,
    workbench.mutations.createIngestionMutation.error,
    workbench.runState.runErrorMessage,
  ]);

  const sourceHealth = workbench.queries.sourceHealthQuery.data?.sources ?? [];
  const tabLabels = useMemo(
    () => [
      { value: "trends" as const, label: "Trends" },
      { value: "extraction" as const, label: "Data Extraction" },
      { value: "sql" as const, label: "SQL Database" },
      { value: "agent" as const, label: "LangGraph Agent" },
    ],
    [],
  );

  return (
    <div className="min-h-screen">
      <div className="mx-auto flex max-w-[1680px] flex-col gap-6 px-4 py-4 md:px-6 md:py-6">
        <AppHeader
          sourceHealth={sourceHealth}
          ingestionStatus={workbench.queries.ingestionQuery.data?.status}
          analysisStatus={workbench.queries.analysisQuery.data?.status}
        />

        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as TabValue)} className="space-y-6">
          <div className="sticky top-4 z-20">
            <TabsList className="backdrop-blur-xl">
              {tabLabels.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>
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
        </Tabs>
      </div>
    </div>
  );
}
