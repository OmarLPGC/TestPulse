import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const project = {
  id: 1,
  name: "Signal API",
  repository_url: "https://github.com/example/signal-api",
  created_at: "2025-01-01T10:00:00Z",
  updated_at: "2025-01-01T10:00:00Z",
};

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
): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve(handler(new URL(String(input), "http://localhost"), init)),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  mockFetch((url) => {
    if (url.pathname === "/projects") {
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
  vi.unstubAllGlobals();
});

describe("TestPulse dashboard", () => {
  it("renders the project list", async () => {
    renderAt("/");

    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Signal API/ })).toHaveLength(2);
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
      url.pathname === "/projects" ? response([]) : response(page()),
    );
    renderAt("/");

    expect(await screen.findByRole("heading", { name: "No projects yet" })).toBeInTheDocument();
    expect(
      screen.getByText(/registered with the TestPulse API/i),
    ).toBeInTheDocument();
  });

  it("sends the selected branch as a history query parameter", async () => {
    const fetchMock = mockFetch((url) => {
      if (url.pathname === "/projects") {
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
      if (url.pathname === "/projects") {
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
      if (url.pathname === "/projects") {
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
      url.pathname === "/projects"
        ? response({ detail: "Database unavailable." }, 500)
        : response(page()),
    );
    renderAt("/");

    expect(await screen.findByRole("alert")).toHaveTextContent("Database unavailable.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("paginates results using the API limit and offset", async () => {
    const fetchMock = mockFetch((url) => {
      if (url.pathname === "/projects") {
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
