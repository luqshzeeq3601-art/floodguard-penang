// Test-only mock of the planned FloodGuard API, serving SYNTHETIC fixtures (see fixtures.mjs).
// Usage: node e2e/mock-api/server.mjs [--scenario=full|gated]   (port 8787)
import { createServer } from "node:http";
import { respond } from "./fixtures.mjs";

const PORT = Number(process.env.MOCK_API_PORT ?? 8787);
const scenario = process.argv.find((a) => a.startsWith("--scenario="))?.split("=")[1] ?? process.env.MOCK_SCENARIO ?? "full";

createServer((req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Content-Type", "application/json");
  const body = req.method === "GET" ? respond(url.pathname, url.searchParams, scenario) : null;
  res.statusCode = body ? 200 : 404;
  res.end(JSON.stringify(body ?? { detail: "Not found" }));
}).listen(PORT, () => console.log(`Synthetic mock API (${scenario}) on http://localhost:${PORT}`));
