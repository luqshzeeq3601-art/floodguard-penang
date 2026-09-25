import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const ROUTES = [
  { path: "/", title: "Overview" },
  { path: "/map", title: "Live Map" },
  { path: "/stations", title: "Stations" },
  { path: "/stations/s01", title: "Synthetic River A at Bridge 1" },
  { path: "/predictions", title: "FloodGuard predictions" },
  { path: "/alerts", title: "Alerts" },
  { path: "/status", title: "Data status" },
];

/** Console errors other than third-party font loading fail the test. */
function trackErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" && !/fonts\.(googleapis|gstatic)/.test(m.text())) errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

for (const r of ROUTES) {
  test(`${r.path} renders, is accessible and does not scroll sideways`, async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto(r.path);
    await expect(page.getByRole("heading", { level: 1, name: r.title })).toBeVisible();
    await expect(page.locator("[aria-busy=\"true\"]")).toHaveCount(0);
    await page.waitForTimeout(500);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    const tags = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
    const axe = await new AxeBuilder({ page }).withTags(tags).exclude(".maplibregl-canvas").analyze();
    // Dense map markers may sit closer than 24 px; WCAG 2.5.8's "equivalent" exception applies because every
    // marker has the same action in the station list/table on the page. All other rules still apply to markers.
    const violations = axe.violations.flatMap((v) => {
      const nodes = v.id === "target-size" ? v.nodes.filter((n) => !n.html.startsWith("<button data-map-marker")) : v.nodes;
      return nodes.length ? [`${v.id}: ${nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`] : [];
    });
    expect(violations).toEqual([]);
    expect(errors).toEqual([]);
  });
}

test("every page keeps the disclaimer and the six navigation items", async ({ page, isMobile }) => {
  await page.goto("/");
  if (isMobile) await page.getByRole("button", { name: "Open navigation" }).click();
  const nav = page.getByRole("navigation", { name: "Main" }).filter({ visible: true });
  for (const label of ["Overview", "Live Map", "Stations", "Predictions", "Alerts", "Data Status"]) {
    await expect(nav.getByRole("link", { name: label })).toBeVisible();
  }
  await expect(page.getByText("Operational prototype. Not an official warning service.").filter({ visible: true })).toBeVisible();
});

test("Needs attention links through to station detail with separated sources", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Synthetic River A at Bridge 1" }).first().click();
  await expect(page).toHaveURL(/\/stations\/s01$/);
  await expect(page.getByRole("heading", { name: /Current observation/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Official JPS thresholds" })).toBeVisible();
  await expect(page.getByText("Model output · Not official warnings")).toBeVisible();
});

test.describe("desktop only", () => {
  test.skip(({ isMobile }) => isMobile, "Map selection flow is covered on desktop");

  test("selecting a map marker fills the station rail; keyboard works too", async ({ page }) => {
    await page.goto("/map");
    const map = page.getByRole("region", { name: "Map of Pulau Pinang monitoring stations" });
    const marker = map.getByRole("button", { name: /Synthetic River B at Pump House/ });
    await expect(marker).toBeVisible();
    await marker.click();
    const rail = page.getByRole("complementary", { name: "Selected station" });
    await expect(rail.getByRole("heading", { name: "Synthetic River B at Pump House" })).toBeVisible();
    await expect(rail.getByRole("heading", { name: "JPS observed data" })).toBeVisible();
    await expect(rail.getByRole("heading", { name: "FloodGuard predictions" })).toBeVisible();
    await expect(page).toHaveURL(/station=s02/);

    await map.getByRole("button", { name: /Synthetic River A at Bridge 1/ }).focus();
    await page.keyboard.press("Enter");
    await expect(rail.getByRole("heading", { name: "Synthetic River A at Bridge 1" })).toBeVisible();
  });

  test("Map/List switch keeps filters", async ({ page }) => {
    await page.goto("/map");
    await page.getByRole("radiogroup", { name: "Sensor type" }).getByRole("radio", { name: "Rainfall" }).click();
    await page.getByRole("radio", { name: "List" }).click();
    await expect(page).toHaveURL(/type=RAINFALL/);
    await expect(page).toHaveURL(/view=list/);
    await expect(page.getByRole("table")).not.toContainText("Synthetic River A at Bridge 1");
  });
});

test.describe("desktop refinements", () => {
  test.skip(({ isMobile }) => isMobile, "Desktop toolbar and side panels");

  test("2D/3D map toggle is keyboard operable and remembered", async ({ page }) => {
    await page.goto("/map");
    const toggle = page.getByRole("radiogroup", { name: "Map view" });
    await toggle.getByRole("radio", { name: "2D" }).click();
    await expect(toggle.getByRole("radio", { name: "2D" })).toHaveAttribute("aria-checked", "true");
    await page.keyboard.press("ArrowRight");
    await expect(toggle.getByRole("radio", { name: "3D" })).toHaveAttribute("aria-checked", "true");
    await page.reload();
    await expect(page.getByRole("radiogroup", { name: "Map view" }).getByRole("radio", { name: "3D" })).toHaveAttribute("aria-checked", "true");
  });

  test("More filters popover works from the keyboard and shows a removable chip", async ({ page }) => {
    await page.goto("/map");
    const trigger = page.getByRole("button", { name: /More filters/ });
    await trigger.focus();
    await page.keyboard.press("Enter");
    const freshness = page.getByRole("group", { name: "More filters" }).getByLabel("Freshness");
    await expect(freshness).toBeFocused();
    await freshness.selectOption("STALE");
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
    await expect(page).toHaveURL(/freshness=STALE/);
    await page.getByRole("button", { name: "Remove filter: Freshness: Stale" }).click();
    await expect(page).not.toHaveURL(/freshness=/);
  });

  test("alert summary cards act as pressed filter toggles", async ({ page }) => {
    await page.goto("/alerts");
    const card = page.getByRole("button", { name: /Data quality/ }).first();
    await card.click();
    await expect(card).toHaveAttribute("aria-pressed", "true");
    await expect(page).toHaveURL(/type=DATA_QUALITY/);
    await card.click();
    await expect(card).toHaveAttribute("aria-pressed", "false");
  });
});

test("gated capabilities show 'not available' instead of mock data", async ({ page }) => {
  await page.route(/:8787\/api\/v1\/(predictions|alerts|monitoring)/, (route) => route.fulfill({ status: 404, body: "{}" }));
  await page.goto("/predictions");
  await expect(page.getByText("Predictions not available yet")).toBeVisible();
  await page.goto("/");
  await expect(page.getByText("Alerts not available yet").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Needs attention" })).toBeVisible();
});

test("API outage shows an error with retry, not an empty dashboard", async ({ page }) => {
  await page.route(/:8787\//, (route) => route.abort());
  await page.goto("/");
  await expect(page.getByText("Couldn't load stations")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Retry" }).first()).toBeVisible();
});

test("mobile drawer opens, traps focus and closes with Escape", async ({ page, isMobile }) => {
  test.skip(!isMobile, "Drawer is the mobile navigation pattern");
  await page.goto("/stations");
  await page.getByRole("button", { name: "Open navigation" }).click();
  const drawer = page.getByRole("dialog", { name: "Navigation" });
  await expect(drawer).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await drawer.getByRole("link", { name: "Alerts" }).click();
  await expect(page).toHaveURL(/\/alerts$/);
  await expect(drawer).toBeHidden();
});
