import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ErrorPage from "./error";
import NotFound from "./not-found";

describe("error and 404 pages (UI-SPEC §7)", () => {
  it("the 404 page's message is its h1", () => {
    render(<NotFound />);
    expect(screen.getByRole("heading", { level: 1, name: "We couldn't find that page." })).toBeInTheDocument();
  });

  it("the error page announces its h1 and offers Try again", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const retry = vi.fn();
    render(<ErrorPage error={new Error("boom")} retry={retry} />);
    expect(screen.getByRole("alert")).toContainElement(screen.getByRole("heading", { level: 1, name: "Something went wrong on our side. Nothing has been published." }));
    screen.getByRole("button", { name: "Try again" }).click();
    expect(retry).toHaveBeenCalled();
    expect(screen.queryByText("boom")).toBeNull();
  });
});
