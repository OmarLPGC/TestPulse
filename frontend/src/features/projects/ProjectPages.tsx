import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useParams } from "react-router-dom";

import { getProjects, getRunHistory, type Project } from "../../api";
import { EmptyState, ErrorState, Icon, LoadingState, NotFound, PulseMark } from "../../components/ui";
import { ReliabilityPage } from "../reliability/ReliabilityPage";
import { RunDetailPage, RunsPage } from "../runs/RunPages";

export function Dashboard() {
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

