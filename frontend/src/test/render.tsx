import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";

/** Serves SYNTHETIC fixture bodies by path; unknown paths 404 (gated capability). */
export function mockFetch(routes: Record<string, unknown>) {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://test");
    const body = routes[url.pathname];
    if (body === "NETWORK_ERROR") throw new TypeError("Failed to fetch");
    if (body === undefined) return new Response(JSON.stringify({ detail: "Not found" }), { status: 404 });
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export function renderRoute(element: ReactElement, path = "/", pattern = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, retryDelay: 0, refetchInterval: false } } });
  const router = createMemoryRouter([{ path: pattern, element }], { initialEntries: [path] });
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}
