import { expect, it } from "vitest";
import { baseSettings } from "@/test/fixtures";
import { deriveConnectionStatus } from "./connection";

const noBroker = {
  ...baseSettings,
  alpaca_api_key: "",
  alpaca_api_secret: "",
  alpaca_base_url: "",
};

const savedBroker = {
  ...baseSettings,
  alpaca_api_key: "PK",
  alpaca_api_secret: "secret",
  alpaca_base_url: "https://paper-api.alpaca.markets",
};

it("reports an empty configuration", () => {
  expect(deriveConnectionStatus(noBroker, "unconfigured", null)).toEqual({
    broker: "unconfigured",
    environment: null,
    environmentVerified: false,
  });
});

it("reports saved keys before a successful probe", () => {
  expect(deriveConnectionStatus(savedBroker, "pending", null)).toEqual({
    broker: "saved",
    environment: "paper",
    environmentVerified: false,
  });
});

it("reports a verified connection and its environment", () => {
  expect(deriveConnectionStatus(savedBroker, "ok", false)).toEqual({
    broker: "connected",
    environment: "live",
    environmentVerified: true,
  });
});

it("reports an unreachable broker with the saved environment", () => {
  const live = {
    ...savedBroker,
    alpaca_base_url: "https://api.alpaca.markets",
  };
  expect(deriveConnectionStatus(live, "error", null)).toEqual({
    broker: "error",
    environment: "live",
    environmentVerified: false,
  });
});
