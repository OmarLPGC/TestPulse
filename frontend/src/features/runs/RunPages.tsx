import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  getRegressions,
  getRunHistory,
  getRunResults,
  getRunSummary,
  isTestOutcome,
  type RegressionReport,
  type RunHistoryItem,
  type RunHistoryPage,
  type RunSummary,
  type TestOutcome,
  type TestResultPage,
} from "../../api";
import {
  EmptyState,
  ErrorState,
  Icon,
  LoadingState,
  Pagination,
  StatusBadge,
  SummaryValue,
} from "../../components/ui";
import { PAGE_SIZE } from "../../constants";
import { formatDate, formatDuration, shortCommit } from "../../utils/formatting";

export function RunsPage({ projectId, branch }: { projectId: number; branch: string }) {
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

export function RunDetailPage({ projectId }: { projectId: number }) {
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
              onChange={(event) => {
                const value = event.target.value;
                setOutcome(isTestOutcome(value) ? value : "");
              }}
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
