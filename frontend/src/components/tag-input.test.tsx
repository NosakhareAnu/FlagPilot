import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { TagInput } from "./tag-input";

afterEach(cleanup);

function Harness({ initial = [] as string[] }) {
  const [v, setV] = useState(initial);
  return (
    <>
      <TagInput label="Included users" values={v} onChange={setV} />
      <output data-testid="out">{v.join("|")}</output>
    </>
  );
}

describe("TagInput", () => {
  it("adds on Enter, ignores duplicates, supports comma lists", () => {
    render(<Harness />);
    const input = screen.getByLabelText("Included users");
    fireEvent.change(input, { target: { value: "alice" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.change(input, { target: { value: "alice, bob" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByTestId("out").textContent).toBe("alice|bob");
  });

  it("removes with the x button and Backspace", () => {
    render(<Harness initial={["a", "b"]} />);
    fireEvent.click(screen.getByLabelText("Remove a from Included users"));
    expect(screen.getByTestId("out").textContent).toBe("b");
    fireEvent.keyDown(screen.getByLabelText("Included users"), { key: "Backspace" });
    expect(screen.getByTestId("out").textContent).toBe("");
  });

  it("rejects over-long identifiers", () => {
    render(<Harness />);
    const input = screen.getByLabelText("Included users");
    fireEvent.change(input, { target: { value: "x".repeat(257) } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByRole("alert").textContent).toContain("256");
    expect(screen.getByTestId("out").textContent).toBe("");
  });
});
