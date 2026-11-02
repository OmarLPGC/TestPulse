import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  createWorkspaceProject,
  getGitHubRepositories,
  type GitHubRepository,
  type GitHubRepositoryPage,
} from "../../api";
import { ErrorState, LoadingState } from "../../components/ui";
import { useWorkspaces } from "./WorkspaceContext";

const REPOSITORIES_PER_PAGE = 25;

export function CreateProjectPage() {
  const { activeWorkspace, refreshProjects, workspaceState } = useWorkspaces();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [repositories, setRepositories] = useState<GitHubRepositoryPage | null>(null);
  const [repositoryState, setRepositoryState] = useState<"loading" | "ready" | "error">("loading");
  const [repositoryError, setRepositoryError] = useState("");
  const [selectedRepository, setSelectedRepository] = useState<GitHubRepository | null>(null);
  const [createWithoutRepository, setCreateWithoutRepository] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!activeWorkspace || activeWorkspace.role !== "owner" || createWithoutRepository) return;
    const controller = new AbortController();
    setRepositoryState("loading");
    getGitHubRepositories(page, REPOSITORIES_PER_PAGE, controller.signal)
      .then((result) => {
        setRepositories(result);
        setRepositoryState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") return;
        setRepositoryError(
          error instanceof Error ? error.message : "Could not load GitHub repositories.",
        );
        setRepositoryState("error");
      });
    return () => controller.abort();
  }, [activeWorkspace, createWithoutRepository, page, retry]);

  if (!activeWorkspace && workspaceState === "loading") {
    return <LoadingState label="Loading your workspace" />;
  }

  if (!activeWorkspace) {
    return (
      <div className="page-container">
        <ErrorState
          message="Create or join a workspace before adding a project."
          onRetry={() => navigate("/")}
        />
      </div>
    );
  }

  if (activeWorkspace.role !== "owner") {
    return (
      <div className="page-container">
        <header className="page-heading projects-heading">
          <div>
            <h1>New project</h1>
            <p>Only workspace owners can connect repositories or create projects.</p>
          </div>
        </header>
        <Link className="text-link" to="/">Return to projects</Link>
      </div>
    );
  }

  const workspaceId = activeWorkspace.id;

  async function saveProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaveError("");
    setSaving(true);
    try {
      const created = await createWorkspaceProject(workspaceId, {
        name: projectName.trim() || selectedRepository?.full_name || "",
        ...(selectedRepository && !createWithoutRepository ? { repository: selectedRepository } : {}),
      });
      refreshProjects();
      navigate(`/project/${created.id}`);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Could not create the project.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-container">
      <div className="page-topline">
        <Link className="breadcrumb-current" to="/">Projects</Link>
        <span className="topline-caption">{activeWorkspace.name}</span>
      </div>
      <header className="page-heading projects-heading">
        <div>
          <h1>Connect a project</h1>
          <p>Choose a repository you can access, or start without connecting one.</p>
        </div>
      </header>

      <form className="project-create-form" onSubmit={saveProject}>
        <label className="form-field">
          <span>Project name</span>
          <input
            autoComplete="off"
            maxLength={120}
            onChange={(event) => setProjectName(event.target.value)}
            placeholder={selectedRepository?.full_name || "Payments API"}
            required={createWithoutRepository}
            value={projectName}
          />
        </label>

        <label className="form-checkbox">
          <input
            checked={createWithoutRepository}
            onChange={(event) => {
              setCreateWithoutRepository(event.target.checked);
              setSelectedRepository(null);
            }}
            type="checkbox"
          />
          <span>Create without connecting a GitHub repository</span>
        </label>

        {!createWithoutRepository && (
          <section aria-labelledby="repository-list-heading" className="repository-picker">
            <div className="section-heading">
              <div>
                <h2 id="repository-list-heading">Repositories you can access</h2>
                <p>Only the selected repository is connected to this project.</p>
              </div>
              {repositories && <span className="section-count">Page {repositories.page}</span>}
            </div>

            {repositoryState === "loading" && (
              <LoadingState compact label="Loading GitHub repositories" />
            )}
            {repositoryState === "error" && (
              <ErrorState
                message={repositoryError}
                onRetry={() => setRetry((current) => current + 1)}
              />
            )}
            {repositoryState === "ready" && repositories?.items.length === 0 && (
              <div className="empty-state repository-empty">
                <h3>No repositories found</h3>
                <p>Check that your GitHub account or organization has granted this installation access.</p>
              </div>
            )}
            {repositoryState === "ready" && repositories && repositories.items.length > 0 && (
              <ul aria-label="GitHub repositories" className="repository-list">
                {repositories.items.map((repository) => (
                  <li key={repository.id}>
                    <button
                      aria-pressed={selectedRepository?.id === repository.id}
                      className={`repository-option${selectedRepository?.id === repository.id ? " selected" : ""}`}
                      onClick={() => setSelectedRepository(repository)}
                      type="button"
                    >
                      <span>
                        <strong>{repository.full_name}</strong>
                        <small>{repository.private ? "Private" : "Public"} repository</small>
                      </span>
                      <span aria-hidden="true" className="repository-selection-mark">
                        {selectedRepository?.id === repository.id ? "Selected" : "Select"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {repositories && (
              <nav aria-label="Repository pages" className="repository-pagination">
                <button
                  disabled={page <= 1 || repositoryState === "loading"}
                  onClick={() => setPage((current) => current - 1)}
                  type="button"
                >
                  Previous repositories
                </button>
                <button
                  disabled={!repositories.has_more || repositoryState === "loading"}
                  onClick={() => setPage((current) => current + 1)}
                  type="button"
                >
                  More repositories
                </button>
              </nav>
            )}
          </section>
        )}

        {saveError && <p className="form-error" role="alert">{saveError}</p>}
        <div className="form-actions">
          <Link className="secondary-button" to="/">Cancel</Link>
          <button
            className="primary-button"
            disabled={saving || (!createWithoutRepository && !selectedRepository)}
            type="submit"
          >
            {saving ? "Creating project…" : "Create project"}
          </button>
        </div>
      </form>
    </div>
  );
}
