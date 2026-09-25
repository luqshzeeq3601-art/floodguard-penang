import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("apiGet", () => {
  it("classifies 404/501 as a gated capability, not a failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 501 })));
    await expect(apiGet("/api/v1/alerts")).rejects.toMatchObject({ kind: "not_available", status: 501 });
  });

  it("classifies network failures as unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const err = await apiGet("/health").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("unreachable");
  });

  it("classifies 5xx as a server error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 503 })));
    await expect(apiGet("/ready")).rejects.toMatchObject({ kind: "server", status: 503 });
  });
});
