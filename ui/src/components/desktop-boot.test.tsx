import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { DesktopBoot } from "./desktop-boot";

it("renders children directly outside a packaged desktop build", () => {
  render(
    <DesktopBoot>
      <div data-testid="app" />
    </DesktopBoot>,
  );

  expect(screen.getByTestId("app")).toBeInTheDocument();
});
