import { useEffect, useMemo, useState } from "react";

import { getReliability, type ReliabilityReport } from "../../api";
import { EmptyState, ErrorState, LoadingState, ReliabilityBadge } from "../../components/ui";
import { formatPercent } from "../../utils/formatting";

export function ReliabilityPage({ projectId, branch }: { projectId: number; branch: string }) {
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

