import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { InfoTip } from "./InfoTip";

describe("InfoTip", () => {
  it("opens with the keyboard, closes on Escape and returns focus", async () => {
    const user = userEvent.setup();
    render(<InfoTip label="About freshness">Derived by FloodGuard.</InfoTip>);
    const button = screen.getByRole("button", { name: "About freshness" });
    await user.tab();
    expect(button).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("note")).toHaveTextContent("Derived by FloodGuard.");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("note")).toBeNull();
    expect(button).toHaveFocus();
  });

  it("closes on outside click", async () => {
    const user = userEvent.setup();
    render(
      <div>
        <InfoTip label="Info">Text</InfoTip>
        <p>outside</p>
      </div>,
    );
    await user.click(screen.getByRole("button", { name: "Info" }));
    expect(screen.getByRole("note")).toBeInTheDocument();
    await user.click(screen.getByText("outside"));
    expect(screen.queryByRole("note")).toBeNull();
  });
});
