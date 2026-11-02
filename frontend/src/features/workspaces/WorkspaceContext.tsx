import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  getWorkspaceProjects,
  getWorkspaces,
  type Project,
  type Workspace,
} from "../../api";

type LoadState = "loading" | "ready" | "error";

interface WorkspaceContextValue {
  workspaces: Workspace[];
  activeWorkspace: Workspace | null;
  setActiveWorkspaceId: (id: number) => void;
  projects: Project[];
  projectsState: LoadState;
  projectsError: string;
  refreshProjects: () => void;
  workspaceState: LoadState;
  workspaceError: string;
  retryWorkspaces: () => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceState, setWorkspaceState] = useState<LoadState>("loading");
  const [workspaceError, setWorkspaceError] = useState("");
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<number | null>(null);
  const [workspaceRetry, setWorkspaceRetry] = useState(0);
  const [projectRetry, setProjectRetry] = useState(0);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsState, setProjectsState] = useState<LoadState>("loading");
  const [projectsError, setProjectsError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setWorkspaceState("loading");
    getWorkspaces(controller.signal)
      .then((items) => {
        setWorkspaces(items);
        setActiveWorkspaceId((current) =>
          current !== null && items.some((workspace) => workspace.id === current)
            ? current
            : (items[0]?.id ?? null),
        );
        setWorkspaceState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") return;
        setWorkspaceError(
          error instanceof Error ? error.message : "Could not load your workspaces.",
        );
        setWorkspaceState("error");
      });
    return () => controller.abort();
  }, [workspaceRetry]);

  const activeWorkspace =
    workspaces.find((workspace) => workspace.id === activeWorkspaceId) ?? null;

  useEffect(() => {
    if (!activeWorkspace) {
      setProjects([]);
      setProjectsState(workspaceState === "ready" ? "ready" : "loading");
      return;
    }

    const controller = new AbortController();
    setProjects([]);
    setProjectsState("loading");
    getWorkspaceProjects(activeWorkspace.id, controller.signal)
      .then((items) => {
        setProjects(items);
        setProjectsState("ready");
        setProjectsError("");
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") return;
        setProjectsError(error instanceof Error ? error.message : "Could not load projects.");
        setProjectsState("error");
      });
    return () => controller.abort();
  }, [activeWorkspace, projectRetry, workspaceState]);

  const value = useMemo(
    () => ({
      workspaces,
      activeWorkspace,
      setActiveWorkspaceId: (id: number) => {
        setProjects([]);
        setProjectsState("loading");
        setActiveWorkspaceId(id);
      },
      projects,
      projectsState,
      projectsError,
      refreshProjects: () => setProjectRetry((current) => current + 1),
      workspaceState,
      workspaceError,
      retryWorkspaces: () => setWorkspaceRetry((current) => current + 1),
    }),
    [
      activeWorkspace,
      projects,
      projectsError,
      projectsState,
      workspaces,
      workspaceError,
      workspaceState,
    ],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspaces(): WorkspaceContextValue {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspaces must be used within WorkspaceProvider.");
  }
  return context;
}
