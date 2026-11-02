export type RunStatus = "pending" | "running" | "completed" | "failed" | "empty";
export type TestOutcome = "passed" | "failed" | "skipped" | "error";
export type Reliability =
  | "stable"
  | "potentially_flaky"
  | "persistently_failing"
  | "insufficient_data";

const TEST_OUTCOMES = new Set<string>(["passed", "failed", "skipped", "error"]);

export function isTestOutcome(value: string): value is TestOutcome {
  return TEST_OUTCOMES.has(value);
}

export interface Project {
  id: number;
  workspace_id: number;
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

export interface AuthenticatedUser {
  id: number;
  login: string;
  name: string | null;
  avatar_url: string | null;
}

export interface Workspace {
  id: number;
  name: string;
  role: "owner" | "member";
}

export interface GitHubRepository {
  id: number;
  full_name: string;
  html_url: string;
  private: boolean;
}

export interface GitHubRepositoryPage {
  items: GitHubRepository[];
  page: number;
  per_page: number;
  has_more: boolean;
}

export interface IngestionToken {
  id: number;
  name: string;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
}

export interface CreatedIngestionToken extends IngestionToken {
  token: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function record(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("TestPulse returned an invalid response.");
  }
  return value as Record<string, unknown>;
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function parseProject(value: unknown): Project {
  const project = record(value);
  const { id, workspace_id, name, repository_url, created_at, updated_at } = project;
  if (
    typeof id !== "number" ||
    !Number.isInteger(id) ||
    typeof workspace_id !== "number" ||
    !Number.isInteger(workspace_id) ||
    typeof name !== "string" ||
    !nullableString(repository_url) ||
    typeof created_at !== "string" ||
    typeof updated_at !== "string"
  ) {
    throw new Error("TestPulse returned an invalid project.");
  }
  return { id, workspace_id, name, repository_url, created_at, updated_at };
}

function csrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const cookie = document.cookie
    .split("; ")
    .find((item) => item.startsWith("testpulse_csrf="));
  return cookie ? decodeURIComponent(cookie.slice("testpulse_csrf=".length)) : null;
}

async function requestJson<T>(
  path: string,
  signal?: AbortSignal,
  init: RequestInit = {},
): Promise<T> {
  let response: Response;
  const headers = new Headers(init.headers);
  if (init.method && !["GET", "HEAD", "OPTIONS"].includes(init.method.toUpperCase())) {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", token);
  }
  try {
    response = await fetch(path, { ...init, headers, credentials: "include", signal });
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
    if (
      response.status === 401 &&
      path !== "/api/v1/auth/me" &&
      typeof window !== "undefined"
    ) {
      window.dispatchEvent(new Event("testpulse:session-expired"));
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
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

export function getCurrentUser(signal?: AbortSignal): Promise<AuthenticatedUser> {
  return requestJson<unknown>("/api/v1/auth/me", signal).then((value) => {
    const user = record(value);
    const { id, github_login, display_name, avatar_url } = user;
    if (
      typeof id !== "number" ||
      !Number.isInteger(id) ||
      typeof github_login !== "string" ||
      !nullableString(display_name) ||
      !nullableString(avatar_url)
    ) {
      throw new Error("TestPulse returned an invalid user session.");
    }
    return { id, login: github_login, name: display_name, avatar_url };
  });
}

export function getGitHubLoginUrl(): string {
  return "/api/v1/auth/github/login";
}

export function logout(): Promise<void> {
  return requestJson<void>("/api/v1/auth/logout", undefined, { method: "POST" });
}

export function getWorkspaces(signal?: AbortSignal): Promise<Workspace[]> {
  return requestJson<unknown>("/api/v1/workspaces", signal).then((value) => {
    if (!Array.isArray(value)) throw new Error("TestPulse returned an invalid workspace list.");
    return value.map((item) => {
      const workspace = record(item);
      const { id, name, role } = workspace;
      if (
        typeof id !== "number" ||
        !Number.isInteger(id) ||
        typeof name !== "string" ||
        (role !== "owner" && role !== "member")
      ) {
        throw new Error("TestPulse returned an invalid workspace.");
      }
      return { id, name, role };
    });
  });
}

export function getWorkspaceProjects(
  workspaceId: number,
  signal?: AbortSignal,
): Promise<Project[]> {
  return requestJson<unknown>("/projects", signal).then((value) => {
    if (!Array.isArray(value)) throw new Error("TestPulse returned an invalid project list.");
    return value.map(parseProject).filter((project) => project.workspace_id === workspaceId);
  });
}

export function getGitHubRepositories(
  page: number,
  perPage: number,
  signal?: AbortSignal,
): Promise<GitHubRepositoryPage> {
  const parameters = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  return requestJson<unknown>(
    `/api/v1/github/repositories?${parameters.toString()}`,
    signal,
  ).then((value) => {
    const pageData = record(value);
    const pageNumber = pageData.page;
    const perPage = pageData.per_page;
    const hasMore = pageData.has_next;
    if (
      !Array.isArray(pageData.items) ||
      typeof pageNumber !== "number" ||
      !Number.isInteger(pageNumber) ||
      typeof perPage !== "number" ||
      !Number.isInteger(perPage) ||
      typeof hasMore !== "boolean"
    ) {
      throw new Error("TestPulse returned an invalid repository page.");
    }
    const items = pageData.items.map((item) => {
      const repository = record(item);
      const { id, full_name, html_url, private: isPrivate } = repository;
      if (
        typeof id !== "number" ||
        !Number.isInteger(id) ||
        typeof full_name !== "string" ||
        typeof html_url !== "string" ||
        typeof isPrivate !== "boolean"
      ) {
        throw new Error("TestPulse returned an invalid GitHub repository.");
      }
      return { id, full_name, html_url, private: isPrivate };
    });
    return { items, page: pageNumber, per_page: perPage, has_more: hasMore };
  });
}

export function createWorkspaceProject(
  workspaceId: number,
  input: { name: string; repository?: GitHubRepository },
): Promise<Project> {
  return requestJson<unknown>("/projects", undefined, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: input.name,
      workspace_id: workspaceId,
      repository_url: input.repository?.html_url ?? null,
    }),
  }).then(async (value) => {
    const project = parseProject(value);
    if (input.repository) {
      try {
        await requestJson(
          `/api/v1/projects/${project.id}/repository`,
          undefined,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              github_repository_id: input.repository.id,
              full_name: input.repository.full_name,
            }),
          },
        );
      } catch (error) {
        const detail = error instanceof Error ? error.message : "Unknown error.";
        throw new Error(`Project was created, but its GitHub repository could not be connected: ${detail}`);
      }
    }
    return project;
  });
}

export function getIngestionTokens(
  projectId: number,
  signal?: AbortSignal,
): Promise<IngestionToken[]> {
  return requestJson<unknown>(
    `/api/v1/projects/${projectId}/ingestion-tokens`,
    signal,
  ).then(parseIngestionTokens);
}

export function createIngestionToken(
  projectId: number,
  name: string,
): Promise<CreatedIngestionToken> {
  return requestJson<unknown>(
    `/api/v1/projects/${projectId}/ingestion-tokens`,
    undefined,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    },
  ).then((value) => {
    const [token] = parseIngestionTokens([value]);
    const created = record(value);
    if (typeof created.token !== "string" || !created.token) {
      throw new Error("TestPulse did not return the new token secret.");
    }
    return { ...token, token: created.token };
  });
}

function parseIngestionTokens(value: unknown): IngestionToken[] {
  if (!Array.isArray(value)) throw new Error("TestPulse returned an invalid token list.");
  return value.map((item) => {
    const token = record(item);
    const { id, name, created_at, expires_at, revoked_at } = token;
    if (
      typeof id !== "number" ||
      !Number.isInteger(id) ||
      typeof name !== "string" ||
      typeof created_at !== "string" ||
      !nullableString(expires_at) ||
      !nullableString(revoked_at)
    ) {
      throw new Error("TestPulse returned an invalid ingestion token.");
    }
    return { id, name, created_at, expires_at, revoked_at };
  });
}

export function revokeIngestionToken(projectId: number, tokenId: number): Promise<void> {
  return requestJson<void>(
    `/api/v1/projects/${projectId}/ingestion-tokens/${tokenId}`,
    undefined,
    { method: "DELETE" },
  );
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
