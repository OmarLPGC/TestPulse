import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { Workspace } from "./api";
import { workflowYaml } from "./features/projects/ProjectSettingsPage";

const project = {
  id: 1,
  name: "Signal API",
  repository_url: "https://github.com/example/signal-api",
  created_at: "2025-01-01T10:00:00Z",
  updated_at: "2025-01-01T10:00:00Z",
};
const authenticatedUser = {
  id: 8,
  login: "omar",
  name: "Omar",
  avatar_url: null,
};
const defaultWorkspace = { id: 1, name: "Engineering", role: "owner" as const };

const historyItem = {
  id: 7,
  project_id: 1,
  commit_sha: "abcdef012345",
  branch: "main",
  report_sha: "report-hash",
  status: "failed",
  duration: 2450,
  ingested_at: "2025-01-02T10:00:00Z",
  completed_at: "2025-01-02T10:00:02Z",
};

function response(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

function page(items: unknown[] = []) {
  return { items, limit: 20, offset: 0, total: items.length };
}

function renderAt(path: string) {
  window.history.replaceState({}, "", path);
  return render(<App />);
}

function mockFetch(
  handler: (url: URL, init?: RequestInit) => Response | Promise<Response>,
  options: {
    authenticated?: boolean;
    user?: typeof authenticatedUser;
    workspaces?: Workspace[];
    projects?: typeof project[];
  } = {},
): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const result = await handler(url, init);
    if (options.authenticated !== false && url.pathname === "/api/v1/auth/me") {
      return response(options.user ?? authenticatedUser);
    }
    if (options.authenticated !== false && url.pathname === "/api/v1/workspaces") {
      return response(options.workspaces ?? [defaultWorkspace]);
    }
    if (
      options.authenticated !== false &&
      url.pathname.match(/^\/api\/v1\/workspaces\/\d+\/projects$/) &&
      init?.method !== "POST"
    ) {
      if (!result.ok) return result;
      const payload = await result.json();
      return Array.isArray(payload) ? result : response(options.projects ?? [project]);
    }
    return result;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  mockFetch((url) => {
    if (url.pathname === "/api/v1/workspaces/1/projects") {
      return response([project]);
    }
    if (url.pathname.endsWith("/runs/7")) {
      return response({
        ...historyItem,
        total: 3,
        passed: 2,
        failed: 1,
        skipped: 0,
        error: 0,
      });
    }
    if (url.pathname.endsWith("/runs")) {
      return response(page([historyItem]));
    }
    return response({});
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TestPulse dashboard", () => {
  it("redirects anonymous visitors to GitHub sign-in without storing credentials", async () => {
    const fetchMock = mockFetch(
      (url) =>
        url.pathname === "/api/v1/auth/me"
          ? response({ detail: "Not signed in." }, 401)
          : response({}),
      { authenticated: false },
    );
    renderAt("/project/1/runs/7");

    expect(await screen.findByRole("heading", { name: "Sign in to TestPulse" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Continue with GitHub" })).toHaveAttribute(
      "href",
      "/api/v1/auth/github/login",
    );
    expect(fetchMock.mock.calls[0][1]?.credentials).toBe("include");
    expect(window.localStorage.length).toBe(0);
  });

  it("signs out through the session endpoint", async () => {
    const fetchMock = mockFetch((url) =>
      url.pathname === "/api/v1/auth/logout" ? response({}, 204) : response({}),
    );
    renderAt("/");

    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in to TestPulse" })).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          String(input) === "/api/v1/auth/logout" &&
          init?.method === "POST" &&
          init.credentials === "include",
      ),
    ).toBe(true);
  });

  it("returns to sign-in when a protected API request reports an expired session", async () => {
    mockFetch((url) =>
      url.pathname === "/api/v1/workspaces/1/projects"
        ? response({ detail: "Session expired." }, 401)
        : response({}),
    );
    renderAt("/");

    expect(await screen.findByRole("heading", { name: "Sign in to TestPulse" })).toBeInTheDocument();
    expect(screen.getByText(/Your session expired/i)).toBeInTheDocument();
  });

  it("switches the project list to the selected workspace", async () => {
    const secondWorkspace = { id: 2, name: "Research", role: "member" as const };
    const fetchMock = mockFetch(
      (url) => {
        if (url.pathname === "/api/v1/workspaces/2/projects") {
          return response([{ ...project, id: 2, name: "Model tests" }]);
        }
        return response({});
      },
      { workspaces: [defaultWorkspace, secondWorkspace] },
    );
    renderAt("/");

    await userEvent.selectOptions(
      await screen.findByRole("combobox", { name: "Active workspace" }),
      "2",
    );
    expect(await screen.findAllByRole("link", { name: /Model tests/ })).toHaveLength(2);
    expect(screen.queryByRole("link", { name: "Connect project" })).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input]) => String(input) === "/api/v1/workspaces/2/projects"),
    ).toBe(true);
  });

  it("shows a clear empty state when GitHub has no accessible repositories", async () => {
    mockFetch((url) =>
      url.pathname === "/api/v1/github/repositories"
        ? response({ items: [], page: 1, per_page: 25, has_more: false })
        : response({}),
    );
    renderAt("/projects/new");

    expect(await screen.findByRole("heading", { name: "Connect a project" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "No repositories found" })).toBeInTheDocument();
    expect(screen.getByText(/granted this installation access/i)).toBeInTheDocument();
  });

  it("paginates through accessible GitHub repositories", async () => {
    const fetchMock = mockFetch((url) =>
      url.pathname === "/api/v1/github/repositories"
        ? response({
            items: [
              {
                id: url.searchParams.get("page") === "2" ? 202 : 101,
                full_name: url.searchParams.get("page") === "2" ? "org/second" : "org/first",
                html_url: "https://github.com/org/repository",
                private: true,
                default_branch: "main",
              },
            ],
            page: Number(url.searchParams.get("page")),
            per_page: 25,
            has_more: url.searchParams.get("page") === "1",
          })
        : response({}),
    );
    renderAt("/projects/new");

    expect(await screen.findByText("org/first")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "More repositories" }));
    expect(await screen.findByText("org/second")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input]) => {
        const url = new URL(String(input), "http://localhost");
        return url.pathname === "/api/v1/github/repositories" && url.searchParams.get("page") === "2";
      }),
    ).toBe(true);
  });

  it("creates a project without connecting a repository when requested", async () => {
    let created = false;
    const newProject = {
      ...project,
      id: 9,
      name: "Local test suite",
      repository_url: null,
    };
    const fetchMock = mockFetch((url, init) => {
      if (url.pathname === "/api/v1/workspaces/1/projects" && init?.method === "POST") {
        created = true;
        return response(newProject);
      }
      if (url.pathname === "/api/v1/workspaces/1/projects") {
        return response(created ? [newProject] : [project]);
      }
      if (url.pathname.endsWith("/runs")) return response(page());
      return response({});
    });
    renderAt("/projects/new");

    await userEvent.click(await screen.findByRole("checkbox", {
      name: "Create without connecting a GitHub repository",
    }));
    await userEvent.type(screen.getByLabelText("Project name"), "Local test suite");
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => {
      const request = fetchMock.mock.calls.find(
        ([input, init]) =>
          String(input) === "/api/v1/workspaces/1/projects" && init?.method === "POST",
      );
      expect(request).toBeDefined();
      expect(JSON.parse(String(request?.[1]?.body))).toEqual({ name: "Local test suite" });
    });
    expect(await screen.findByRole("heading", { name: "Local test suite" })).toBeInTheDocument();
  });

  it("renders a safe workflow snippet with one-time secret references and fork protection", () => {
    const workflow = workflowYaml(17);
    expect(workflow).toContain("if: always()");
    expect(workflow).toContain("TESTPULSE_TOKEN: ${{ secrets.TESTPULSE_TOKEN }}");
    expect(workflow).toContain("Authorization: Bearer ${TESTPULSE_TOKEN}");
    expect(workflow).toContain("head.repo.full_name == github.repository");
    expect(workflow).toContain("TESTPULSE_PROJECT_ID: ${{ vars.TESTPULSE_PROJECT_ID || '17' }}");
    expect(workflow).not.toContain("pull_request_target");
    expect(workflow).not.toContain("secret-value");
  });

  it("shows a newly issued ingestion token once and lists it without repeating its secret", async () => {
    const savedToken = {
      id: 5,
      name: "Existing CI",
      created_at: "2025-02-01T10:00:00Z",
      expires_at: null,
      revoked_at: null,
    };
    mockFetch((url, init) => {
      if (url.pathname === "/api/v1/projects/1/ingestion-tokens" && init?.method === "POST") {
        return response({
          id: 6,
          name: "Nightly",
          created_at: "2025-02-02T10:00:00Z",
          expires_at: null,
          revoked_at: null,
          token: "testpulse-one-time-secret",
        });
      }
      if (url.pathname === "/api/v1/projects/1/ingestion-tokens") {
        return response([savedToken]);
      }
      return response({});
    });
    renderAt("/project/1/settings");

    expect(await screen.findByText("Existing CI")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Token name"), "Nightly");
    await userEvent.click(screen.getByRole("button", { name: "Create token" }));

    expect(await screen.findByText("testpulse-one-time-secret")).toBeInTheDocument();
    expect(screen.getByText("Copy your token now")).toBeInTheDocument();
    expect(screen.getByText(/shown once/i)).toBeInTheDocument();
    expect(screen.getByText("testpulse-one-time-secret").closest(".token-list-item")).toBeNull();
    expect(screen.getByRole("heading", { name: "GitHub Actions" })).toBeInTheDocument();
    expect(screen.getByText(/pull requests from forks/i)).toBeInTheDocument();
  });

  it("revokes an ingestion token only after confirmation", async () => {
    const token = {
      id: 5,
      name: "Release workflow",
      created_at: "2025-02-01T10:00:00Z",
      expires_at: null,
      revoked_at: null,
    };
    const fetchMock = mockFetch((url, init) => {
      if (url.pathname.endsWith("/ingestion-tokens/5") && init?.method === "DELETE") {
        return response({}, 204);
      }
      if (url.pathname.endsWith("/ingestion-tokens")) return response([token]);
      return response({});
    });
    renderAt("/project/1/settings");

    await userEvent.click(await screen.findByRole("button", { name: "Revoke" }));
    expect(screen.getByText("Revoke this token?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("Revoked")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          String(input) === "/api/v1/projects/1/ingestion-tokens/5" &&
          init?.method === "DELETE",
      ),
    ).toBe(true);
  });

  it("does not offer project or token administration to workspace members", async () => {
    mockFetch(() => response({}), {
      workspaces: [{ id: 1, name: "Engineering", role: "member" }],
    });
    renderAt("/project/1/settings");

    expect(await screen.findByText(/Only workspace owners can create or revoke project tokens/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create token" })).not.toBeInTheDocument();
  });

  it("renders the project list", async () => {
    renderAt("/");

    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(await screen.findAllByRole("link", { name: /Signal API/ })).toHaveLength(2);
  });

  it("shows a real summary for the latest project execution", async () => {
    renderAt("/project/1");

    const summary = await screen.findByRole("region", {
      name: "Latest execution summary",
    });
    await waitFor(() => expect(summary).toHaveTextContent("3 tests"));
    expect(summary).toHaveTextContent("3 tests");
    expect(summary).toHaveTextContent("2 passed");
    expect(summary).toHaveTextContent("1 failed");
    expect(within(summary).getByRole("link", { name: "View run" })).toHaveAttribute(
      "href",
      "/project/1/runs/7",
    );
  });

  it("explains when there are no projects", async () => {
    mockFetch((url) =>
      url.pathname === "/api/v1/workspaces/1/projects" ? response([]) : response(page()),
    );
    renderAt("/");

    expect(await screen.findByRole("heading", { name: "No projects yet" })).toBeInTheDocument();
    expect(screen.getByText(/Connect a GitHub repository/i)).toBeInTheDocument();
  });

  it("sends the selected branch as a history query parameter", async () => {
    const fetchMock = mockFetch((url) => {
      if (url.pathname === "/api/v1/workspaces/1/projects") {
        return response([project]);
      }
      if (url.pathname.endsWith("/runs/7")) {
        return response({
          ...historyItem,
          total: 2,
          passed: 1,
          failed: 1,
          skipped: 0,
          error: 0,
        });
      }
      if (url.pathname.endsWith("/runs")) {
        return response(
          page([
            historyItem,
            { ...historyItem, id: 8, branch: "release/1.0", status: "completed" },
          ]),
        );
      }
      return response({});
    });
    renderAt("/project/1");

    const branchFilter = await screen.findByRole("combobox", { name: "Filter by branch" });
    await screen.findByRole("option", { name: "main" });
    await userEvent.selectOptions(branchFilter, "main");

    await waitFor(() => {
      const matchingRequest = fetchMock.mock.calls.find(([input]) => {
        const url = new URL(String(input), "http://localhost");
        return url.pathname.endsWith("/runs") && url.searchParams.get("branch") === "main";
      });
      expect(matchingRequest).toBeDefined();
    });
  });

  it("shows failed test results, messages, and traces as text", async () => {
    const unsafeText = "<img src=x onerror=alert(1)>";
    mockFetch((url) => {
      if (url.pathname === "/api/v1/workspaces/1/projects") {
        return response([project]);
      }
      if (url.pathname.endsWith("/results")) {
        return response(
          page([
            {
              id: 12,
              test_case_id: 3,
              name: "test_checkout",
              class_name: "tests.test_orders",
              outcome: "failed",
              duration: 86,
              error_message: unsafeText,
              traceback: `AssertionError: ${unsafeText}`,
            },
          ]),
        );
      }
      if (url.pathname.endsWith("/regressions")) {
        return response({
          project_id: 1,
          run_id: 7,
          branch: "main",
          previous_run_id: 6,
          regressions: [],
        });
      }
      if (url.pathname.endsWith("/runs/7")) {
        return response({
          ...historyItem,
          total: 1,
          passed: 0,
          failed: 1,
          skipped: 0,
          error: 0,
        });
      }
      return response(page([historyItem]));
    });
    renderAt("/project/1/runs/7");

    expect(await screen.findByRole("heading", { name: "test_checkout" })).toBeInTheDocument();
    expect(screen.getByText(unsafeText)).toBeInTheDocument();
    expect(screen.getByText(`AssertionError: ${unsafeText}`)).toBeInTheDocument();
    expect(document.querySelector(".failure-detail img")).not.toBeInTheDocument();
    expect(screen.getByText("No new regressions in this run.")).toBeInTheDocument();
  });

  it("shows potential instability and observed failure statistics", async () => {
    mockFetch((url) => {
      if (url.pathname === "/api/v1/workspaces/1/projects") {
        return response([project]);
      }
      if (url.pathname.endsWith("/analysis/reliability")) {
        return response({
          branch: null,
          window_size: 20,
          minimum_observations: 5,
          tests: [
            {
              test_case_id: 21,
              name: "test_intermittent_timeout",
              class_name: "tests.test_network",
              observations: 10,
              passed: 8,
              failed: 2,
              errors: 0,
              failure_rate: 0.2,
              reliability: "potentially_flaky",
              potentially_flaky: true,
            },
            {
              test_case_id: 22,
              name: "test_database_connection",
              class_name: "tests.test_database",
              observations: 10,
              passed: 0,
              failed: 10,
              errors: 0,
              failure_rate: 1,
              reliability: "persistently_failing",
              potentially_flaky: false,
            },
          ],
        });
      }
      return response(page());
    });
    renderAt("/project/1/reliability");

    expect(await screen.findByText("test_intermittent_timeout")).toBeInTheDocument();
    expect(screen.getByText("Potentially flaky")).toHaveClass(
      "reliability-potentially_flaky",
    );
    expect(screen.getByText("Persistent failure")).toHaveClass(
      "reliability-persistently_failing",
    );
    const row = screen.getByRole("row", { name: /test_intermittent_timeout/ });
    expect(within(row).getByText("20%")).toBeInTheDocument();
    expect(within(row).getByText("10")).toBeInTheDocument();
  });

  it("shows an actionable error when the API fails", async () => {
    mockFetch((url) =>
      url.pathname === "/api/v1/workspaces/1/projects"
        ? response({ detail: "Database unavailable." }, 500)
        : response(page()),
    );
    renderAt("/");

    expect(await screen.findByRole("alert")).toHaveTextContent("Database unavailable.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("paginates results using the API limit and offset", async () => {
    const fetchMock = mockFetch((url) => {
      if (url.pathname === "/api/v1/workspaces/1/projects") {
        return response([project]);
      }
      if (url.pathname.endsWith("/results")) {
        const offset = Number(url.searchParams.get("offset") ?? 0);
        return response({
          items: [
            {
              id: 30,
              test_case_id: 30,
              name: "test_page_two",
              class_name: null,
              outcome: "passed",
              duration: 10,
              error_message: null,
              traceback: null,
            },
          ],
          limit: 20,
          offset,
          total: 21,
        });
      }
      if (url.pathname.endsWith("/regressions")) {
        return response({
          project_id: 1,
          run_id: 7,
          branch: "main",
          previous_run_id: 6,
          regressions: [],
        });
      }
      if (url.pathname.endsWith("/runs/7")) {
        return response({
          ...historyItem,
          total: 21,
          passed: 21,
          failed: 0,
          skipped: 0,
          error: 0,
        });
      }
      return response({
        ...page([historyItem]),
        total: 21,
      });
    });
    renderAt("/project/1/runs/7");

    await screen.findByRole("heading", { name: "test_page_two" });
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));

    await waitFor(() => {
      const resultRequest = fetchMock.mock.calls.find(([input]) => {
        const url = new URL(String(input), "http://localhost");
        return url.pathname.endsWith("/results") && url.searchParams.get("offset") === "20";
      });
      expect(resultRequest).toBeDefined();
    });
  });
});
