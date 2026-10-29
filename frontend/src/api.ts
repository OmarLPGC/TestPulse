export type RunStatus = "pending" | "running" | "completed" | "failed" | "empty";
export type TestOutcome = "passed" | "failed" | "skipped" | "error";
export type Reliability =
  | "stable"
  | "potentially_flaky"
  | "persistently_failing"
  | "insufficient_data";

export interface Project {
  id: number;
  name: string;
  repository_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface RunHistoryItem {
  id: number;
  project_id: number;
  commit_sha: string | null;
  branch: string | null;
  report_sha: string | null;
  status: RunStatus;
  duration: number | null;
  ingested_at: string;
  completed_at: string | null;
}

export interface RunHistoryPage {
  items: RunHistoryItem[];
  limit: number;
  offset: number;
  total: number;
}

export interface RunSummary extends RunHistoryItem {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  error: number;
}

export interface TestResult {
  id: number;
  test_case_id: number;
  name: string;
  class_name: string | null;
  outcome: TestOutcome;
  duration: number | null;
  error_message: string | null;
  traceback: string | null;
}

export interface TestResultPage {
  items: TestResult[];
  limit: number;
  offset: number;
  total: number;
}

export interface ReliabilityTest {
  test_case_id: number;
  name: string;
  class_name: string | null;
  observations: number;
  passed: number;
  failed: number;
  errors: number;
  failure_rate: number;
  reliability: Reliability;
  potentially_flaky: boolean;
}

export interface ReliabilityReport {
  branch: string | null;
  window_size: number;
  minimum_observations: number;
  tests: ReliabilityTest[];
}

export interface Regression {
  test_case_id: number;
  name: string;
  class_name: string | null;
  previous_outcome: TestOutcome;
  current_outcome: TestOutcome;
}

export interface RegressionReport {
  project_id: number;
  run_id: number;
  branch: string | null;
  previous_run_id: number | null;
  regressions: Regression[];
}

async function requestJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { signal });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw error;
    }
    throw new Error("Could not reach TestPulse. Check that the API is running and try again.");
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}.`;
    try {
      const payload: unknown = await response.json();
      if (
        typeof payload === "object" &&
        payload !== null &&
        "detail" in payload &&
        typeof payload.detail === "string"
      ) {
        detail = payload.detail;
      }
    } catch (error) {
      if (!(error instanceof SyntaxError)) {
        throw error;
      }
    }
    throw new Error(detail);
  }

  try {
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof SyntaxError) {
      throw new Error("TestPulse returned an unreadable response.");
    }
    throw error;
  }
}

export function getProjects(signal?: AbortSignal): Promise<Project[]> {
  return requestJson<Project[]>("/projects", signal);
}

export function getRunHistory(
  projectId: number,
  options: { branch?: string; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<RunHistoryPage> {
  const parameters = new URLSearchParams();
  parameters.set("limit", String(options.limit ?? 20));
  parameters.set("offset", String(options.offset ?? 0));
  if (options.branch) {
    parameters.set("branch", options.branch);
  }
  return requestJson<RunHistoryPage>(
    `/api/v1/projects/${projectId}/runs?${parameters.toString()}`,
    signal,
  );
}

export function getRunSummary(
  projectId: number,
  runId: number,
  signal?: AbortSignal,
): Promise<RunSummary> {
  return requestJson<RunSummary>(`/api/v1/projects/${projectId}/runs/${runId}`, signal);
}

export function getRunResults(
  projectId: number,
  runId: number,
  options: { outcome?: TestOutcome; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<TestResultPage> {
  const parameters = new URLSearchParams();
  parameters.set("limit", String(options.limit ?? 20));
  parameters.set("offset", String(options.offset ?? 0));
  if (options.outcome) {
    parameters.set("status", options.outcome);
  }
  return requestJson<TestResultPage>(
    `/api/v1/projects/${projectId}/runs/${runId}/results?${parameters.toString()}`,
    signal,
  );
}

export function getReliability(
  projectId: number,
  branch?: string,
  signal?: AbortSignal,
): Promise<ReliabilityReport> {
  const parameters = new URLSearchParams();
  if (branch) {
    parameters.set("branch", branch);
  }
  const query = parameters.size > 0 ? `?${parameters.toString()}` : "";
  return requestJson<ReliabilityReport>(
    `/api/v1/projects/${projectId}/analysis/reliability${query}`,
    signal,
  );
}

export function getRegressions(
  projectId: number,
  runId: number,
  signal?: AbortSignal,
): Promise<RegressionReport> {
  return requestJson<RegressionReport>(
    `/api/v1/projects/${projectId}/runs/${runId}/regressions`,
    signal,
  );
}
