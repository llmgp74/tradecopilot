import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ProviderIcon } from "./provider-icon";

it("renders the models.dev logo for a provider", () => {
  const { container } = render(<ProviderIcon provider="deepseek" />);

  const image = container.querySelector("img");
  expect(image).not.toBeNull();
  expect(image).toHaveAttribute("src", "https://models.dev/logos/deepseek.svg");
});

it("hides the image after a load error", () => {
  const { container } = render(<ProviderIcon provider="deepseek" />);

  fireEvent.error(container.querySelector("img") as HTMLImageElement);

  expect(container.querySelector("img")).toBeNull();
});

it("renders nothing without a provider id", () => {
  const { container } = render(<ProviderIcon provider="" />);

  expect(container.querySelector("img")).toBeNull();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
