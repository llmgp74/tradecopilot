import type { ReasoningOption } from "./catalog";

/** One option shown in a reasoning menu. */
export interface ReasoningChoice {
  value: string;
  label: string;
}

const LABELS: Record<string, string> = {
  off: "Off",
  on: "On",
  minimal: "Minimal",
  low: "Low",
  medium: "Medium",
  high: "High",
  xhigh: "Extra high",
  max: "Max",
};

/**
 * Flattens a model's reasoning options for display.
 *
 * Mirrors the backend: Off is offered when the model declares `none` or a
 * toggle. Effort values keep their catalog order. Toggle-only models offer Off
 * and On. Budget-only models offer the three levels mapped by the backend.
 *
 * @param options - Catalog reasoning options.
 * @returns The menu choices.
 */
export function reasoningChoices(options: ReasoningOption[]): ReasoningChoice[] {
  const effort = options.find(
    (option): option is Extract<ReasoningOption, { type: "effort" }> =>
      option.type === "effort",
  );
  const hasToggle = options.some((option) => option.type === "toggle");
  if (effort) {
    const values = effort.values.filter((value) => value !== "none");
    const choices = values.map((value) => ({
      value,
      label: LABELS[value] ?? value,
    }));
    if (hasToggle || effort.values.includes("none")) {
      return [{ value: "off", label: LABELS.off }, ...choices];
    }
    return choices;
  }
  if (hasToggle) {
    return [
      { value: "off", label: LABELS.off },
      { value: "on", label: LABELS.on },
    ];
  }
  if (options.some((option) => option.type === "budget_tokens")) {
    return ["off", "low", "medium", "high"].map((value) => ({
      value,
      label: LABELS[value],
    }));
  }
  return [];
}
