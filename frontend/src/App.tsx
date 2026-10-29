import { useEffect, useMemo, useState } from "react";
import {
  BrowserRouter,
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
  useParams,
} from "react-router-dom";

import {
  getProjects,
  getReliability,
  getRegressions,
  getRunHistory,
  getRunResults,
  getRunSummary,
  type Project,
  type ReliabilityReport,
  type RegressionReport,
  type RunHistoryItem,
  type RunHistoryPage,
  type RunSummary,
  type TestOutcome,
  type TestResultPage,
} from "./api";

const PAGE_SIZE = 20;

export default function App() {
  return (
    <BrowserRouter>
      <Dashboard />
    </BrowserRouter>
  );
}

function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectState, setProjectState] = useState<"loading" | "ready" | "error">("loading");
  const [projectError, setProjectError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setProjectState("loading");
    getProjects(controller.signal)
      .then((items) => {
        setProjects(items);
        setProjectState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") {
          return;
        }
        setProjectError(error instanceof Error ? error.message : "Could not load projects.");
        setProjectState("error");
      });
    return () => controller.abort();
  }, [retry]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link aria-label="TestPulse home" className="brand" to="/">
          <PulseMark />
          <span>testpulse</span>
        </Link>

        <nav aria-label="Main navigation" className="side-navigation">
          <NavLink className={({ isActive }) => navClass(isActive)} end to="/">
            <Icon name="grid" />
            <span>Projects</span>
            <span className="nav-count">{projects.length}</span>
          </NavLink>
        </nav>

        <div className="sidebar-section">
          <p className="sidebar-heading">Your projects</p>
          {projectState === "loading" && <span className="sidebar-note">Loading projects…</span>}
          {projectState === "error" && (
            <span className="sidebar-note" role="status">
              Project list unavailable
            </span>
          )}
          {projectState === "ready" && projects.length === 0 && (
            <span className="sidebar-note">No projects yet</span>
          )}
          {projects.map((project) => (
            <NavLink
              aria-label={`Open ${project.name}`}
              className={({ isActive }) => `project-link${isActive ? " active" : ""}`}
              key={project.id}
              to={`/project/${project.id}`}
            >
              <span aria-hidden="true" className="project-dot" />
              <span className="project-link-name">{project.name}</span>
            </NavLink>
          ))}
        </div>

        <div className="sidebar-footer">
          <span className="connection-indicator" />
          <span>Test history, in focus.</span>
        </div>
      </aside>

      <main className="main-panel">
        <Routes>
          <Route
            element={
              <ProjectsPage
                error={projectError}
                onRetry={() => setRetry((value) => value + 1)}
                projects={projects}
                state={projectState}
              />
            }
            path="/"
          />
          <Route
            element={
              <ProjectWorkspace
                onRetryProjects={() => setRetry((value) => value + 1)}
                projectState={projectState}
                projects={projects}
              />
            }
            path="/project/:projectId/*"
          />
          <Route element={<NotFound />} path="*" />
        </Routes>
      </main>
    </div>
  );
}

function navClass(isActive: boolean): string {
  return `primary-link${isActive ? " active" : ""}`;
}

function ProjectsPage({
  projects,
  state,
  error,
  onRetry,
}: {
  projects: Project[];
  state: "loading" | "ready" | "error";
  error: string;
  onRetry: () => void;
}) {
  return (
    <div className="page-container projects-page">
      <div className="page-topline">
        <span className="breadcrumb-current">Projects</span>
        <span className="topline-caption">A clearer view of test reliability</span>
      </div>
      <header className="page-heading projects-heading">
        <div>
          <h1>Projects</h1>
          <p>Choose a project to explore its test history and reliability.</p>
        </div>
        {state === "ready" && <span className="heading-count">{projects.length} projects</span>}
      </header>

      {state === "loading" && <LoadingState label="Loading your projects" />}
      {state === "error" && <ErrorState message={error} onRetry={onRetry} />}
      {state === "ready" && projects.length === 0 && (
        <EmptyState
          title="No projects yet"
          description="Projects appear here after the first one is registered with the TestPulse API."
        />
      )}
      {state === "ready" && projects.length > 0 && (
        <div aria-label="Projects" className="project-grid">
          {projects.map((project) => (
            <Link className="project-card" key={project.id} to={`/project/${project.id}`}>
              <div className="project-card-mark">
                <PulseMark />
              </div>
              <div className="project-card-copy">
                <h2>{project.name}</h2>
                <p>{project.repository_url || "Repository URL not set"}</p>
              </div>
              <span className="project-card-open" aria-hidden="true">
                <Icon name="arrow" />
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectWorkspace({
  projects,
  projectState,
  onRetryProjects,
}: {
  projects: Project[];
  projectState: "loading" | "ready" | "error";
  onRetryProjects: () => void;
}) {
  const { projectId: projectIdParam } = useParams();
  const location = useLocation();
  const projectId = Number(projectIdParam);
  const project = projects.find((item) => item.id === projectId);
  const runsViewActive =
    location.pathname === `/project/${projectId}` ||
    location.pathname.startsWith(`/project/${projectId}/runs/`);
  const [branches, setBranches] = useState<string[]>([]);
  const [branch, setBranch] = useState("");
  const [branchError, setBranchError] = useState("");

  useEffect(() => {
    if (
      projectState !== "ready" ||
      !project ||
      !Number.isInteger(projectId) ||
      projectId < 1
    ) {
      return;
    }
    const controller = new AbortController();
    getRunHistory(projectId, { limit: 100 }, controller.signal)
      .then((page) => {
        setBranches(
          [...new Set(page.items.map((run) => run.branch).filter((value): value is string => !!value))]
            .sort((left, right) => left.localeCompare(right)),
        );
        setBranchError("");
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") {
          return;
        }
        setBranchError(
          error instanceof Error ? error.message : "Could not load available branches.",
        );
      });
    return () => controller.abort();
  }, [project, projectId, projectState]);

  useEffect(() => {
    setBranch("");
  }, [projectId]);

  if (projectState === "loading") {
    return <LoadingState label="Loading project" />;
  }
  if (projectState === "error") {
    return <ErrorState message="The project list could not be loaded." onRetry={onRetryProjects} />;
  }
  if (!Number.isInteger(projectId) || projectId < 1 || !project) {
    return (
      <div className="page-container">
        <ErrorState message="This project could not be found." onRetry={onRetryProjects} />
      </div>
    );
  }

  return (
    <div className="page-container workspace">
      <div className="workspace-topbar">
        <div aria-label="Breadcrumb" className="breadcrumbs">
          <Link to="/">Projects</Link>
          <Icon name="chevron" />
          <span>{project.name}</span>
        </div>
        <label className="branch-control">
          <Icon name="branch" />
          <span className="visually-hidden">Filter by branch</span>
          <select
            aria-label="Filter by branch"
            onChange={(event) => setBranch(event.target.value)}
            value={branch}
          >
            <option value="">All branches</option>
            {branches.map((branchName) => (
              <option key={branchName} value={branchName}>
                {branchName}
              </option>
            ))}
          </select>
          <Icon name="chevron" />
        </label>
      </div>
      {branchError && (
        <div className="inline-notice" role="status">
          Branch suggestions are unavailable: {branchError}
        </div>
      )}

      <div className="project-title-row">
        <div>
          <h1>{project.name}</h1>
          {project.repository_url && (
            <a className="repository-link" href={project.repository_url} rel="noreferrer" target="_blank">
              {project.repository_url}
              <Icon name="external" />
            </a>
          )}
        </div>
      </div>

      <nav aria-label="Project views" className="project-tabs">
        <Link
          aria-current={runsViewActive ? "page" : undefined}
          className={`project-tab${runsViewActive ? " active" : ""}`}
          to={`/project/${projectId}`}
        >
          <Icon name="pulse" />
          Runs
        </Link>
        <NavLink
          className={({ isActive }) => `project-tab${isActive ? " active" : ""}`}
          to={`/project/${projectId}/reliability`}
        >
          <Icon name="stability" />
          Reliability
        </NavLink>
      </nav>

      <Routes>
        <Route element={<RunsPage branch={branch} projectId={projectId} />} index />
        <Route element={<RunDetailPage projectId={projectId} />} path="runs/:runId" />
        <Route
          element={<ReliabilityPage branch={branch} projectId={projectId} />}
          path="reliability"
        />
        <Route element={<NotFound />} path="*" />
      </Routes>
    </div>
  );
}

function RunsPage({ projectId, branch }: { projectId: number; branch: string }) {
  const [page, setPage] = useState<RunHistoryPage | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    setOffset(0);
  }, [branch, projectId]);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    getRunHistory(
      projectId,
      { branch: branch || undefined, limit: PAGE_SIZE, offset },
      controller.signal,
    )
      .then((result) => {
        setPage(result);
        setState("ready");
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof Error && requestError.name === "AbortError") {
          return;
        }
        setError(
          requestError instanceof Error ? requestError.message : "Could not load run history.",
        );
        setState("error");
      });
    return () => controller.abort();
  }, [branch, offset, projectId, retry]);

  return (
    <section aria-labelledby="history-heading" className="content-section">
      <div className="section-heading">
        <div>
          <h2 id="history-heading">Run history</h2>
          <p>Every report, newest first.</p>
        </div>
        {state === "ready" && page && (
          <span className="section-count">{page.total} executions</span>
        )}
      </div>

      {state === "loading" && <LoadingState label="Loading run history" compact />}
      {state === "error" && (
        <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} />
      )}
      {state === "ready" && page && page.items.length === 0 && (
        <EmptyState
          title={branch ? "No runs on this branch" : "No runs yet"}
          description={
            branch
              ? "Try another branch or choose all branches to see the full history."
              : "Send a JUnit XML report from your CI workflow to start building a history."
          }
        />
      )}
      {state === "ready" && page && page.items.length > 0 && (
        <>
          <LatestRunSummary projectId={projectId} run={page.items[0]} />
          <div className="run-ledger">
            {page.items.map((run, index) => (
              <RunRow
                key={run.id}
                projectId={projectId}
                run={run}
                featured={offset === 0 && index === 0}
              />
            ))}
          </div>
          <Pagination
            limit={page.limit}
            offset={page.offset}
            onChange={setOffset}
            total={page.total}
          />
        </>
      )}
    </section>
  );
}

function LatestRunSummary({
  projectId,
  run,
}: {
  projectId: number;
  run: RunHistoryItem;
}) {
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    getRunSummary(projectId, run.id, controller.signal)
      .then((result) => {
        setSummary(result);
        setState("ready");
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof Error && requestError.name === "AbortError") {
          return;
        }
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Could not load the latest run summary.",
        );
        setState("error");
      });
    return () => controller.abort();
  }, [projectId, retry, run.id]);

  return (
    <section aria-label="Latest execution summary" className="latest-summary">
      <div className="latest-summary-heading">
        <div>
          <span className="latest-summary-label">Latest execution</span>
          <strong>
            <span className="mono">#{run.id}</span>
            <span className="latest-commit">{shortCommit(run.commit_sha)}</span>
          </strong>
          <span className="latest-summary-meta">
            {run.branch || "Branch not set"} <span aria-hidden="true">·</span>{" "}
            {formatDate(run.ingested_at)}
          </span>
        </div>
        <StatusBadge status={run.status} />
      </div>
      {state === "loading" && <LoadingState compact label="Loading run summary" />}
      {state === "error" && (
        <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} />
      )}
      {state === "ready" && summary && (
        <div className="latest-summary-content">
          <div className="latest-summary-counts">
            <span>
              <strong>{summary.total}</strong> tests
            </span>
            <span className="outcome-passed">
              <strong>{summary.passed}</strong> passed
            </span>
            <span className="outcome-failed">
              <strong>{summary.failed}</strong> failed
            </span>
            <span className="outcome-error">
              <strong>{summary.error}</strong> errors
            </span>
            <span className="outcome-skipped">
              <strong>{summary.skipped}</strong> skipped
            </span>
            <span className="latest-duration">{formatDuration(summary.duration)}</span>
          </div>
          <Link className="latest-summary-link" to={`/project/${projectId}/runs/${run.id}`}>
            View run
            <Icon name="arrow" />
          </Link>
        </div>
      )}
    </section>
  );
}

function RunRow({
  run,
  projectId,
  featured,
}: {
  run: RunHistoryItem;
  projectId: number;
  featured: boolean;
}) {
  return (
    <Link
      aria-label={`Run ${run.id}, ${run.status}, ${run.commit_sha || "no commit"}`}
      className={`run-row${featured ? " featured" : ""}`}
      to={`/project/${projectId}/runs/${run.id}`}
    >
      <span className={`run-marker status-${run.status}`} />
      <span className="run-main">
        <span className="run-identity">
          <span className="run-commit">{shortCommit(run.commit_sha)}</span>
          <span className="run-branch">{run.branch || "Branch not set"}</span>
        </span>
        <span className="run-meta">
          <span>Run #{run.id}</span>
          <span>{formatDate(run.ingested_at)}</span>
        </span>
      </span>
      <StatusBadge status={run.status} />
      <span className="run-duration">{formatDuration(run.duration)}</span>
      <span aria-hidden="true" className="run-open">
        <Icon name="chevron" />
      </span>
    </Link>
  );
}

function RunDetailPage({ projectId }: { projectId: number }) {
  const { runId: runIdParam } = useParams();
  const runId = Number(runIdParam);
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [regressions, setRegressions] = useState<RegressionReport | null>(null);
  const [detailState, setDetailState] = useState<"loading" | "ready" | "error">("loading");
  const [detailError, setDetailError] = useState("");
  const [results, setResults] = useState<TestResultPage | null>(null);
  const [resultsState, setResultsState] = useState<"loading" | "ready" | "error">("loading");
  const [resultsError, setResultsError] = useState("");
  const [outcome, setOutcome] = useState<TestOutcome | "">("");
  const [offset, setOffset] = useState(0);
  const [retry, setRetry] = useState(0);
  const [resultsRetry, setResultsRetry] = useState(0);

  useEffect(() => {
    if (!Number.isInteger(runId) || runId < 1) {
      setDetailError("This run could not be found.");
      setDetailState("error");
      return;
    }
    const controller = new AbortController();
    setDetailState("loading");
    Promise.all([
      getRunSummary(projectId, runId, controller.signal),
      getRegressions(projectId, runId, controller.signal),
    ])
      .then(([runSummary, regressionReport]) => {
        setSummary(runSummary);
        setRegressions(regressionReport);
        setDetailState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") {
          return;
        }
        setDetailError(error instanceof Error ? error.message : "Could not load this run.");
        setDetailState("error");
      });
    return () => controller.abort();
  }, [projectId, retry, runId]);

  useEffect(() => {
    setOffset(0);
  }, [outcome]);

  useEffect(() => {
    const controller = new AbortController();
    setResultsState("loading");
    getRunResults(
      projectId,
      runId,
      { outcome: outcome || undefined, limit: PAGE_SIZE, offset },
      controller.signal,
    )
      .then((result) => {
        setResults(result);
        setResultsState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") {
          return;
        }
        setResultsError(
          error instanceof Error ? error.message : "Could not load test results.",
        );
        setResultsState("error");
      });
    return () => controller.abort();
  }, [offset, outcome, projectId, resultsRetry, runId]);

  if (detailState === "loading") {
    return <LoadingState label="Loading run details" />;
  }
  if (detailState === "error" || !summary || !regressions) {
    return (
      <ErrorState
        message={detailError || "Run details are unavailable."}
        onRetry={() => setRetry((value) => value + 1)}
      />
    );
  }

  return (
    <div className="run-detail">
      <div className="detail-heading">
        <div>
          <Link className="back-link" to={`/project/${projectId}`}>
            <Icon name="chevron-left" />
            Run history
          </Link>
          <h2>
            <span className="mono">#{summary.id}</span>
            <span className="heading-divider">/</span>
            {shortCommit(summary.commit_sha)}
          </h2>
          <p>
            {summary.branch || "Branch not set"} <span className="muted-separator">·</span>{" "}
            {formatDate(summary.ingested_at)}
          </p>
        </div>
        <StatusBadge status={summary.status} />
      </div>

      <section aria-label="Run summary" className="summary-strip">
        <SummaryValue label="Tests" value={summary.total} />
        <SummaryValue label="Passed" tone="passed" value={summary.passed} />
        <SummaryValue label="Failed" tone="failed" value={summary.failed} />
        <SummaryValue label="Errors" tone="error" value={summary.error} />
        <SummaryValue label="Skipped" tone="skipped" value={summary.skipped} />
        <SummaryValue label="Duration" value={formatDuration(summary.duration)} />
      </section>

      <section aria-labelledby="regressions-heading" className="regression-panel">
        <div className="section-heading">
          <div>
            <h3 id="regressions-heading">Regressions</h3>
            <p>
              {regressions.previous_run_id
                ? `Compared with run #${regressions.previous_run_id} on ${
                    regressions.branch || "this branch"
                  }.`
                : "There is no earlier run on this branch to compare."}
            </p>
          </div>
          <span className="section-count">{regressions.regressions.length} detected</span>
        </div>
        {regressions.regressions.length === 0 ? (
          <p className="quiet-empty">No new regressions in this run.</p>
        ) : (
          <ul className="regression-list">
            {regressions.regressions.map((regression) => (
              <li key={regression.test_case_id}>
                <span className="status-dot status-failed" />
                <span className="test-name-block">
                  <strong>{regression.name}</strong>
                  {regression.class_name && <small>{regression.class_name}</small>}
                </span>
                <span className="outcome-change">
                  <span className={`outcome-text outcome-${regression.previous_outcome}`}>
                    {regression.previous_outcome}
                  </span>
                  <Icon name="arrow" />
                  <span className={`outcome-text outcome-${regression.current_outcome}`}>
                    {regression.current_outcome}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="results-heading" className="content-section results-section">
        <div className="section-heading results-heading">
          <div>
            <h3 id="results-heading">Test results</h3>
            <p>Failure messages and traces are shown as plain text.</p>
          </div>
          <label className="outcome-control">
            <span className="visually-hidden">Filter results by status</span>
            <select
              aria-label="Filter results by status"
              onChange={(event) => setOutcome(event.target.value as TestOutcome | "")}
              value={outcome}
            >
              <option value="">All outcomes</option>
              <option value="failed">Failed</option>
              <option value="error">Errors</option>
              <option value="passed">Passed</option>
              <option value="skipped">Skipped</option>
            </select>
          </label>
        </div>
        {resultsState === "loading" && <LoadingState label="Loading test results" compact />}
        {resultsState === "error" && (
          <ErrorState
            message={resultsError}
            onRetry={() => setResultsRetry((value) => value + 1)}
          />
        )}
        {resultsState === "ready" && results && results.items.length === 0 && (
          <EmptyState
            title={outcome ? `No ${outcome} tests` : "This run has no test results"}
            description={
              outcome
                ? "Choose another outcome to see more results."
                : "The report was valid, but it did not contain any test cases."
            }
          />
        )}
        {resultsState === "ready" && results && results.items.length > 0 && (
          <>
            <div className="result-list">
              {results.items.map((result) => (
                <article className="result-item" key={result.id}>
                  <div className="result-title-row">
                    <span className={`status-dot status-${result.outcome}`} />
                    <div className="test-name-block">
                      <h4>{result.name}</h4>
                      {result.class_name && <span>{result.class_name}</span>}
                    </div>
                    <StatusBadge status={result.outcome} />
                    <span className="result-duration">{formatDuration(result.duration)}</span>
                  </div>
                  {(result.error_message || result.traceback) && (
                    <div className="failure-detail">
                      {result.error_message && (
                        <p className="failure-message">{result.error_message}</p>
                      )}
                      {result.traceback && (
                        <details>
                          <summary>Show error trace</summary>
                          <pre>{result.traceback}</pre>
                        </details>
                      )}
                    </div>
                  )}
                </article>
              ))}
            </div>
            <Pagination
              limit={results.limit}
              offset={results.offset}
              onChange={setOffset}
              total={results.total}
            />
          </>
        )}
      </section>
    </div>
  );
}

function ReliabilityPage({ projectId, branch }: { projectId: number; branch: string }) {
  const [report, setReport] = useState<ReliabilityReport | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    getReliability(projectId, branch || undefined, controller.signal)
      .then((result) => {
        setReport(result);
        setState("ready");
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof Error && requestError.name === "AbortError") {
          return;
        }
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Could not load reliability analysis.",
        );
        setState("error");
      });
    return () => controller.abort();
  }, [branch, projectId, retry]);

  const attentionTests = useMemo(
    () =>
      report?.tests.filter(
        (test) => test.potentially_flaky || test.reliability === "persistently_failing",
      ) ?? [],
    [report],
  );
  const flakyCount = report?.tests.filter((test) => test.potentially_flaky).length ?? 0;
  const insufficientCount =
    report?.tests.filter((test) => test.reliability === "insufficient_data").length ?? 0;

  return (
    <section aria-labelledby="reliability-heading" className="content-section reliability-page">
      <div className="section-heading">
        <div>
          <h2 id="reliability-heading">Reliability</h2>
          <p>
            The last {report?.window_size ?? 20} valid results per test, excluding skipped runs.
            Classification starts at {report?.minimum_observations ?? 5} observations.
          </p>
        </div>
        {state === "ready" && (
          <span className="section-count">
            {flakyCount} potentially flaky
          </span>
        )}
      </div>

      {state === "loading" && <LoadingState label="Analyzing test reliability" compact />}
      {state === "error" && (
        <ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} />
      )}
      {state === "ready" && report && attentionTests.length === 0 && (
        <EmptyState
          title={branch ? "No reliability issues on this branch" : "No unstable tests found"}
          description={
            insufficientCount > 0
              ? `${insufficientCount} tests need more history before they can be classified.`
              : "No tests alternate between passing and failing in the current observation window."
          }
        />
      )}
      {state === "ready" && attentionTests.length > 0 && (
        <div className="reliability-table-wrap">
          <table className="reliability-table">
            <thead>
              <tr>
                <th scope="col">Test</th>
                <th scope="col">Classification</th>
                <th scope="col">Passed</th>
                <th scope="col">Failed</th>
                <th scope="col">Errors</th>
                <th scope="col">Failure rate</th>
                <th scope="col">Observations</th>
              </tr>
            </thead>
            <tbody>
              {attentionTests.map((test) => (
                <tr key={test.test_case_id}>
                  <td className="reliability-test">
                    <strong>{test.name}</strong>
                    {test.class_name && <small>{test.class_name}</small>}
                  </td>
                  <td>
                    <ReliabilityBadge reliability={test.reliability} />
                  </td>
                  <td className="numeric-cell outcome-passed">{test.passed}</td>
                  <td className="numeric-cell outcome-failed">{test.failed}</td>
                  <td className="numeric-cell outcome-error">{test.errors}</td>
                  <td className="numeric-cell">{formatPercent(test.failure_rate)}</td>
                  <td className="numeric-cell">{test.observations}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {insufficientCount > 0 && (
            <p className="table-footnote">
              {insufficientCount} additional tests need more history before they can be classified.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function SummaryValue({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: TestOutcome;
}) {
  return (
    <div className="summary-value">
      <span className="summary-label">{label}</span>
      <strong className={tone ? `outcome-${tone}` : ""}>{value}</strong>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`status-badge status-${status}`}>
      <span className="status-dot" />
      {status}
    </span>
  );
}

function ReliabilityBadge({ reliability }: { reliability: string }) {
  const label =
    reliability === "persistently_failing" ? "Persistent failure" : "Potentially flaky";
  return <span className={`reliability-badge reliability-${reliability}`}>{label}</span>;
}

function Pagination({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  const page = Math.floor(offset / limit);
  const pages = Math.ceil(total / limit);
  if (pages <= 1) {
    return null;
  }
  return (
    <nav aria-label="Pagination" className="pagination">
      <span>
        {offset + 1}–{Math.min(offset + limit, total)} of {total}
      </span>
      <div>
        <button disabled={page === 0} onClick={() => onChange((page - 1) * limit)} type="button">
          <Icon name="chevron-left" />
          Previous
        </button>
        <span className="pagination-page">
          {page + 1} / {pages}
        </span>
        <button
          disabled={page + 1 >= pages}
          onClick={() => onChange((page + 1) * limit)}
          type="button"
        >
          Next
          <Icon name="chevron" />
        </button>
      </div>
    </nav>
  );
}

function LoadingState({ label, compact = false }: { label: string; compact?: boolean }) {
  return (
    <div aria-busy="true" aria-live="polite" className={`loading-state${compact ? " compact" : ""}`}>
      <span className="loading-pulse" />
      {label}
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="error-state" role="alert">
      <div>
        <strong>Something went wrong</strong>
        <p>{message}</p>
      </div>
      <button className="secondary-button" onClick={onRetry} type="button">
        Try again
      </button>
    </div>
  );
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="empty-state">
      <div aria-hidden="true" className="empty-mark">
        <PulseMark />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

function NotFound() {
  return (
    <div className="page-container">
      <EmptyState
        title="Page not found"
        description="This TestPulse page does not exist. Return to your project list to continue."
      />
      <Link className="text-link" to="/">
        Go to projects
      </Link>
    </div>
  );
}

function shortCommit(commit: string | null): string {
  return commit ? commit.slice(0, 7) : "No commit";
}

function formatDuration(duration: number | null): string {
  if (duration === null) {
    return "—";
  }
  if (duration < 1000) {
    return `${duration} ms`;
  }
  return `${(duration / 1000).toFixed(1)} s`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function PulseMark() {
  return (
    <svg aria-hidden="true" className="pulse-mark" fill="none" viewBox="0 0 32 32">
      <path
        d="M3 17h6l3.2-8 5.1 15 3.2-9H29"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.2"
      />
    </svg>
  );
}

function Icon({ name }: { name: string }) {
  const common = {
    "aria-hidden": true as const,
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.8,
    viewBox: "0 0 20 20",
  };

  switch (name) {
    case "grid":
      return (
        <svg {...common}>
          <rect height="6" rx="1" width="6" x="3" y="3" />
          <rect height="6" rx="1" width="6" x="11" y="3" />
          <rect height="6" rx="1" width="6" x="3" y="11" />
          <rect height="6" rx="1" width="6" x="11" y="11" />
        </svg>
      );
    case "branch":
      return (
        <svg {...common}>
          <circle cx="6" cy="4" r="2" />
          <circle cx="6" cy="16" r="2" />
          <circle cx="15" cy="7" r="2" />
          <path d="M6 6v8M8 5c4 0 7 0 7 0v.5M8 15h2a5 5 0 0 0 5-5V9" />
        </svg>
      );
    case "pulse":
      return (
        <svg {...common}>
          <path d="M2 10h4l2.2-5 3.6 10 2.4-6H18" />
        </svg>
      );
    case "stability":
      return (
        <svg {...common}>
          <path d="M10 2.5 17 6v4.5c0 3.7-2.7 5.9-7 7-4.3-1.1-7-3.3-7-7V6l7-3.5Z" />
          <path d="m7 10 2 2 4-4" />
        </svg>
      );
    case "arrow":
      return (
        <svg {...common}>
          <path d="M4 10h11M10 5l5 5-5 5" />
        </svg>
      );
    case "chevron":
      return (
        <svg {...common}>
          <path d="m7 4 6 6-6 6" />
        </svg>
      );
    case "chevron-left":
      return (
        <svg {...common}>
          <path d="m13 4-6 6 6 6" />
        </svg>
      );
    case "external":
      return (
        <svg {...common}>
          <path d="M11 4h5v5M16 4 9 11" />
          <path d="M14 11v4a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4" />
        </svg>
      );
    default:
      return null;
  }
}
