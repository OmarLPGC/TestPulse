import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useParams } from "react-router-dom";

import { getRunHistory, type Project } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { EmptyState, ErrorState, Icon, LoadingState, NotFound, PulseMark } from "../../components/ui";
import { ReliabilityPage } from "../reliability/ReliabilityPage";
import { RunDetailPage, RunsPage } from "../runs/RunPages";
import { CreateProjectPage } from "../workspaces/CreateProjectPage";
import { useWorkspaces } from "../workspaces/WorkspaceContext";
import { ProjectSettingsPage } from "./ProjectSettingsPage";

export function Dashboard() {
  const { session, signOut } = useAuth();
  const {
    activeWorkspace,
    projects,
    projectsState,
    projectsError,
    refreshProjects,
    setActiveWorkspaceId,
    workspaceError,
    workspaceState,
    workspaces,
    retryWorkspaces,
  } = useWorkspaces();
  const [signOutError, setSignOutError] = useState("");

  async function handleSignOut() {
    setSignOutError("");
    try {
      await signOut();
    } catch (error) {
      setSignOutError(error instanceof Error ? error.message : "Could not sign out.");
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link aria-label="TestPulse home" className="brand" to="/">
          <PulseMark />
          <span>testpulse</span>
        </Link>

        <div className="workspace-switcher">
          <label htmlFor="active-workspace">Workspace</label>
          {workspaceState === "loading" && <span className="sidebar-note">Loading…</span>}
          {workspaceState === "ready" && workspaces.length === 0 && (
            <span className="sidebar-note">No workspaces available</span>
          )}
          {workspaceState === "ready" && workspaces.length > 0 && (
            <>
              <select
                aria-label="Active workspace"
                id="active-workspace"
                onChange={(event) => setActiveWorkspaceId(Number(event.target.value))}
                value={activeWorkspace?.id ?? ""}
              >
                {workspaces.map((workspace) => (
                  <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
                ))}
              </select>
              {activeWorkspace && <span className="workspace-role">{activeWorkspace.role}</span>}
            </>
          )}
          {workspaceState === "error" && (
            <span className="sidebar-note" role="status">{workspaceError}</span>
          )}
        </div>

        <nav aria-label="Main navigation" className="side-navigation">
          <NavLink className={({ isActive }) => navClass(isActive)} end to="/">
            <Icon name="grid" />
            <span>Projects</span>
            <span className="nav-count">{projects.length}</span>
          </NavLink>
        </nav>

        <div className="sidebar-section">
          <p className="sidebar-heading">Your projects</p>
          {projectsState === "loading" && <span className="sidebar-note">Loading projects…</span>}
          {projectsState === "error" && (
            <span className="sidebar-note" role="status">
              Project list unavailable
            </span>
          )}
          {projectsState === "ready" && projects.length === 0 && (
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
          {session.status === "authenticated" && (
            <>
              {session.user.avatar_url && (
                <img alt="" className="user-avatar" src={session.user.avatar_url} />
              )}
              <span className="user-login">{session.user.name || session.user.login}</span>
            </>
          )}
          <button
            className="text-button sign-out-button"
            onClick={() => void handleSignOut()}
            type="button"
          >
            Sign out
          </button>
        </div>
        {signOutError && <p className="sidebar-error" role="alert">{signOutError}</p>}
      </aside>

      <main className="main-panel">
        {workspaceState === "error" ? (
          <div className="page-container">
            <ErrorState message={workspaceError} onRetry={retryWorkspaces} />
          </div>
        ) : (
        <Routes>
          <Route element={<CreateProjectPage />} path="/projects/new" />
          <Route
            element={
              <ProjectsPage
                error={projectsError}
                onRetry={refreshProjects}
                projects={projects}
                state={projectsState}
              />
            }
            path="/"
          />
          <Route
            element={
              <ProjectWorkspace
                onRetryProjects={refreshProjects}
                projectState={projectsState}
                projects={projects}
              />
            }
            path="/project/:projectId/*"
          />
          <Route element={<NotFound />} path="*" />
        </Routes>
        )}
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
  const { activeWorkspace } = useWorkspaces();

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
        <div className="projects-heading-actions">
          {state === "ready" && <span className="heading-count">{projects.length} projects</span>}
          {activeWorkspace?.role === "owner" ? (
            <Link className="primary-button" to="/projects/new">Connect project</Link>
          ) : (
            <span className="role-explanation">Workspace members can view projects; owners connect them.</span>
          )}
        </div>
      </header>

      {state === "loading" && <LoadingState label="Loading your projects" />}
      {state === "error" && <ErrorState message={error} onRetry={onRetry} />}
      {state === "ready" && !activeWorkspace && (
        <EmptyState
          title="No workspaces available"
          description="You need to belong to a workspace before you can view projects."
        />
      )}
      {state === "ready" && activeWorkspace && projects.length === 0 && (
        <EmptyState
          title="No projects yet"
          description="Connect a GitHub repository or create a project without one to start building test history."
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
        <NavLink
          className={({ isActive }) => `project-tab${isActive ? " active" : ""}`}
          to={`/project/${projectId}/settings`}
        >
          CI setup
        </NavLink>
      </nav>

      <Routes>
        <Route element={<RunsPage branch={branch} projectId={projectId} />} index />
        <Route element={<RunDetailPage projectId={projectId} />} path="runs/:runId" />
        <Route
          element={<ReliabilityPage branch={branch} projectId={projectId} />}
          path="reliability"
        />
        <Route element={<ProjectSettingsPage projectId={projectId} />} path="settings" />
        <Route element={<NotFound />} path="*" />
      </Routes>
    </div>
  );
}
