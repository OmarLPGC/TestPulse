import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  createIngestionToken,
  getIngestionTokens,
  revokeIngestionToken,
  type CreatedIngestionToken,
  type IngestionToken,
} from "../../api";
import { ErrorState, LoadingState } from "../../components/ui";
import { useWorkspaces } from "../workspaces/WorkspaceContext";

export function ProjectSettingsPage({ projectId }: { projectId: number }) {
  const { activeWorkspace } = useWorkspaces();
  const [tokens, setTokens] = useState<IngestionToken[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [tokenName, setTokenName] = useState("");
  const [createdToken, setCreatedToken] = useState<CreatedIngestionToken | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (activeWorkspace?.role !== "owner") {
      setTokens([]);
      setState("ready");
      return;
    }
    const controller = new AbortController();
    setState("loading");
    getIngestionTokens(projectId, controller.signal)
      .then((items) => {
        setTokens(items);
        setState("ready");
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof Error && requestError.name === "AbortError") return;
        setError(
          requestError instanceof Error ? requestError.message : "Could not load project tokens.",
        );
        setState("error");
      });
    return () => controller.abort();
  }, [activeWorkspace?.role, projectId, retry]);

  async function issueToken(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const created = await createIngestionToken(projectId, tokenName.trim());
      setCreatedToken(created);
      const metadata: IngestionToken = {
        id: created.id,
        name: created.name,
        created_at: created.created_at,
        expires_at: created.expires_at,
        revoked_at: created.revoked_at,
      };
      setTokens((current) => [metadata, ...current]);
      setTokenName("");
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Could not create an ingestion token.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function copyText(value: string, copiedMessage: string, fallbackMessage: string) {
    try {
      await navigator.clipboard.writeText(value);
      setNotice(copiedMessage);
    } catch {
      setNotice(fallbackMessage);
    }
  }

  async function revokeToken(tokenId: number) {
    setBusy(true);
    setError("");
    try {
      await revokeIngestionToken(projectId, tokenId);
      setTokens((current) =>
        current.map((token) =>
          token.id === tokenId ? { ...token, revoked_at: new Date().toISOString() } : token,
        ),
      );
      setConfirmRevoke(null);
      setNotice("Token revoked. Workflows using it can no longer upload reports.");
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Could not revoke the token.",
      );
    } finally {
      setBusy(false);
    }
  }

  const canManageTokens = activeWorkspace?.role === "owner";

  return (
    <div className="page-container project-settings-page">
      <div className="page-topline">
        <Link className="breadcrumb-current" to={`/project/${projectId}`}>Project</Link>
        <span className="topline-caption">CI setup</span>
      </div>
      <header className="page-heading projects-heading">
        <div>
          <h1>CI setup</h1>
          <p>Manage project-scoped upload credentials and connect your test workflow.</p>
        </div>
      </header>

      <section aria-labelledby="token-heading" className="settings-section">
        <div className="section-heading">
          <div>
            <h2 id="token-heading">Ingestion tokens</h2>
            <p>Each token can only upload reports to this project.</p>
          </div>
        </div>

        {!canManageTokens && (
          <p className="inline-notice" role="status">
            Only workspace owners can create or revoke project tokens.
          </p>
        )}

        {canManageTokens && (
          <form className="token-create-form" onSubmit={issueToken}>
            <label className="form-field">
              <span>Token name</span>
              <input
                maxLength={100}
                onChange={(event) => setTokenName(event.target.value)}
                placeholder="GitHub Actions"
                required
                value={tokenName}
              />
            </label>
            <button className="primary-button" disabled={busy || !tokenName.trim()} type="submit">
              Create token
            </button>
          </form>
        )}

        {createdToken && (
          <div aria-labelledby="new-token-heading" className="one-time-token" role="status">
            <h3 id="new-token-heading">Copy your token now</h3>
            <p>This secret is shown once. Save it as <code>TESTPULSE_TOKEN</code> in GitHub.</p>
            <div className="token-copy-row">
              <code className="token-value">{createdToken.token}</code>
              <button
                className="secondary-button"
                onClick={() =>
                  void copyText(
                    createdToken.token,
                    "Token copied. Save it in your GitHub Actions secret now.",
                    "Clipboard unavailable. Select and copy the token before leaving this page.",
                  )
                }
                type="button"
              >
                Copy token
              </button>
              <button
                className="text-button"
                onClick={() => setCreatedToken(null)}
                type="button"
              >
                Dismiss secret
              </button>
            </div>
          </div>
        )}

        {notice && <p className="settings-notice" role="status">{notice}</p>}
        {error && <ErrorState message={error} onRetry={() => setRetry((current) => current + 1)} />}
        {state === "loading" && <LoadingState compact label="Loading project tokens" />}
        {state === "error" && !error && (
          <ErrorState message="Project tokens are unavailable." onRetry={() => setRetry((current) => current + 1)} />
        )}
        {state === "ready" && tokens.length === 0 && (
          <p className="empty-inline">No ingestion tokens have been created for this project.</p>
        )}
        {state === "ready" && tokens.length > 0 && (
          <ul aria-label="Project ingestion tokens" className="token-list">
            {tokens.map((token) => (
              <li className="token-list-item" key={token.id}>
                <div>
                  <strong>{token.name}</strong>
                  <small>
                    Created {new Date(token.created_at).toLocaleDateString()}
                    {token.expires_at ? ` · Expires ${new Date(token.expires_at).toLocaleDateString()}` : ""}
                  </small>
                  {token.revoked_at && <span className="token-revoked">Revoked</span>}
                </div>
                {canManageTokens && !token.revoked_at && (
                  confirmRevoke === token.id ? (
                    <span className="revoke-confirm">
                      <span>Revoke this token?</span>
                      <button
                        disabled={busy}
                        onClick={() => void revokeToken(token.id)}
                        type="button"
                      >
                        Confirm
                      </button>
                      <button onClick={() => setConfirmRevoke(null)} type="button">Cancel</button>
                    </span>
                  ) : (
                    <button
                      className="text-button danger-text"
                      onClick={() => setConfirmRevoke(token.id)}
                      type="button"
                    >
                      Revoke
                    </button>
                  )
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="workflow-heading" className="settings-section workflow-section">
        <div className="section-heading">
          <div>
            <h2 id="workflow-heading">GitHub Actions</h2>
            <p>Upload JUnit results even when tests fail, without putting the token in workflow text.</p>
          </div>
          <button
            className="secondary-button"
            onClick={() =>
              void copyText(
                workflowYaml(projectId),
                "Workflow copied to the clipboard.",
                "Clipboard unavailable. Select and copy the workflow text.",
              )
            }
            type="button"
          >
            Copy workflow
          </button>
        </div>
        <pre className="workflow-code"><code>{workflowYaml(projectId)}</code></pre>
        <ol className="workflow-instructions">
          <li>Add the generated workflow to <code>.github/workflows/testpulse.yml</code>.</li>
          <li>Save the one-time token as repository secret <code>TESTPULSE_TOKEN</code>.</li>
          <li>Set repository variable <code>TESTPULSE_URL</code> to this installation and <code>TESTPULSE_PROJECT_ID</code> to {projectId}.</li>
        </ol>
        <div className="inline-notice fork-warning" role="note">
          GitHub does not provide repository secrets to workflows triggered by pull requests from forks.
          The upload step is skipped for those runs while tests still execute. For a separate trusted
          upload, use a workflow started from the default branch and treat fork artifacts as untrusted;
          do not use <code>pull_request_target</code> to check out or run fork code.
        </div>
      </section>
    </div>
  );
}

export function workflowYaml(projectId: number): string {
  return `name: TestPulse
on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install -r requirements.txt
      - name: Run tests and write JUnit report
        run: python -m pytest --junitxml=test-results.xml
      - name: Upload report to TestPulse
        if: always() && (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository)
        env:
          TESTPULSE_TOKEN: \${{ secrets.TESTPULSE_TOKEN }}
          TESTPULSE_URL: \${{ vars.TESTPULSE_URL }}
          TESTPULSE_PROJECT_ID: \${{ vars.TESTPULSE_PROJECT_ID || '${projectId}' }}
          TESTPULSE_COMMIT: \${{ github.sha }}
          TESTPULSE_BRANCH: \${{ github.head_ref || github.ref_name }}
          TESTPULSE_RUN_ID: \${{ github.run_id }}
          TESTPULSE_RUN_ATTEMPT: \${{ github.run_attempt }}
          TESTPULSE_EVENT: \${{ github.event_name }}
          TESTPULSE_PULL_REQUEST: \${{ github.event.pull_request.number || '' }}
          TESTPULSE_REPOSITORY: \${{ github.repository }}
        run: |
          if [ -z "\${TESTPULSE_TOKEN:-}" ]; then
            echo "TestPulse upload skipped: TESTPULSE_TOKEN is unavailable."
            exit 0
          fi
          if [ ! -f test-results.xml ]; then
            echo "TestPulse upload skipped: test-results.xml was not created."
            exit 0
          fi
          TESTPULSE_URL="\${TESTPULSE_URL%/}"
          curl --fail --silent --show-error \\
            --request POST "\${TESTPULSE_URL}/api/v1/projects/\${TESTPULSE_PROJECT_ID}/runs" \\
            --header "Authorization: Bearer \${TESTPULSE_TOKEN}" \\
            --header "Content-Type: application/xml" \\
            --header "X-Commit-SHA: \${TESTPULSE_COMMIT}" \\
            --header "X-Branch: \${TESTPULSE_BRANCH}" \\
            --header "X-CI-Source: github-actions" \\
            --header "X-CI-Run-ID: \${TESTPULSE_RUN_ID}" \\
            --header "X-CI-Run-Attempt: \${TESTPULSE_RUN_ATTEMPT}" \\
            --header "X-CI-Event: \${TESTPULSE_EVENT}" \\
            --header "X-CI-Pull-Request: \${TESTPULSE_PULL_REQUEST}" \\
            --header "X-CI-Repository: \${TESTPULSE_REPOSITORY}" \\
            --header "Idempotency-Key: \${TESTPULSE_REPOSITORY}-\${TESTPULSE_RUN_ID}-\${TESTPULSE_RUN_ATTEMPT}-\${TESTPULSE_PROJECT_ID}" \\
            --data-binary @test-results.xml`;
}
