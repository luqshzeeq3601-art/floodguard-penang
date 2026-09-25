import axe from "axe-core";

/** axe in jsdom; colour contrast needs real layout and is checked in the Playwright run instead. */
export async function axeViolations(node: Element) {
  const res = await axe.run(node, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
  return res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}
