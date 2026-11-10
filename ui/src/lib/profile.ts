import type { Profile, ProfilePatch } from "./api";

/** Fields whose change triggers a confirmation prompt. */
const CONFIRMED_FIELDS: (keyof ProfilePatch)[] = [
  "position_cap_pct",
  "sector_exclusions",
  "execution",
];

/**
 * Compares a list by value.
 *
 * @param left - Current list.
 * @param right - Edited list.
 * @returns True when the lists differ.
 */
function listChanged(left: string[], right: string[]): boolean {
  return (
    left.length !== right.length || left.some((value, index) => value !== right[index])
  );
}

/**
 * Builds the patch containing only changed profile fields.
 *
 * @param original - Profile loaded from the server.
 * @param draft - Edited profile.
 * @returns The partial update.
 */
export function profileChanges(original: Profile, draft: Profile): ProfilePatch {
  const patch: ProfilePatch = {};
  if (draft.risk_band !== original.risk_band) {
    patch.risk_band = draft.risk_band;
  }
  if (draft.position_cap_pct !== original.position_cap_pct) {
    patch.position_cap_pct = draft.position_cap_pct;
  }
  if (listChanged(original.sector_exclusions, draft.sector_exclusions)) {
    patch.sector_exclusions = draft.sector_exclusions;
  }
  if (draft.horizon !== original.horizon) {
    patch.horizon = draft.horizon;
  }
  if (listChanged(original.watchlist, draft.watchlist)) {
    patch.watchlist = draft.watchlist;
  }
  if (listChanged(original.source_preferences, draft.source_preferences)) {
    patch.source_preferences = draft.source_preferences;
  }
  if (
    draft.execution.autonomous !== original.execution.autonomous ||
    draft.execution.max_order_notional !== original.execution.max_order_notional
  ) {
    patch.execution = draft.execution;
  }
  return patch;
}

/**
 * Whether a patch needs a confirmation prompt before saving.
 *
 * @param patch - Partial update.
 * @returns True when the patch touches a hard constraint or execution.
 */
export function requiresConfirmation(patch: ProfilePatch): boolean {
  return CONFIRMED_FIELDS.some((field) => field in patch);
}
