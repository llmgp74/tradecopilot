import { useState } from "react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { getProfile, patchProfile, type Profile, type ProfilePatch } from "@/lib/api";
import { profileChanges, requiresConfirmation } from "@/lib/profile";
import { useResource } from "@/lib/use-resource";
import type { DialogProps } from "./portfolio";

const RISK_BANDS = ["conservative", "moderate", "aggressive"] as const;
const HORIZONS = ["intraday", "days", "weeks", "months"] as const;

/**
 * Parses a comma-separated input into a trimmed list.
 *
 * @param value - Raw input.
 * @param uppercase - Whether to uppercase each item.
 * @returns The cleaned list.
 */
function parseList(value: string, uppercase = false): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => (uppercase ? item.toUpperCase() : item));
}

/**
 * Renders the editable profile fields.
 *
 * List fields keep their raw text while typing and parse on save, so a comma
 * or a trailing space is not stripped mid-entry.
 *
 * @param props - Loaded profile.
 * @returns The form.
 */
function ProfileForm({ profile }: { profile: Profile }) {
  const [baseline, setBaseline] = useState<Profile>(profile);
  const [draft, setDraft] = useState<Profile>(profile);
  const [exclusionsText, setExclusionsText] = useState(
    profile.sector_exclusions.join(", "),
  );
  const [watchlistText, setWatchlistText] = useState(profile.watchlist.join(", "));
  const [sourcesText, setSourcesText] = useState(profile.source_preferences.join(", "));
  const [pending, setPending] = useState<ProfilePatch | null>(null);
  const [saving, setSaving] = useState(false);

  const applySaved = (updated: Profile) => {
    setBaseline(updated);
    setDraft(updated);
    setExclusionsText(updated.sector_exclusions.join(", "));
    setWatchlistText(updated.watchlist.join(", "));
    setSourcesText(updated.source_preferences.join(", "));
  };

  const save = async (patch: ProfilePatch) => {
    setSaving(true);
    try {
      const updated = await patchProfile(patch);
      applySaved(updated);
      toast.success("Profile updated.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Update failed.");
    } finally {
      setSaving(false);
      setPending(null);
    }
  };

  const submit = () => {
    const finalProfile: Profile = {
      ...draft,
      sector_exclusions: parseList(exclusionsText),
      watchlist: parseList(watchlistText, true),
      source_preferences: parseList(sourcesText),
    };
    const patch = profileChanges(baseline, finalProfile);
    if (Object.keys(patch).length === 0) {
      return;
    }
    if (requiresConfirmation(patch)) {
      setPending(patch);
      return;
    }
    void save(patch);
  };

  const numberValue = (value: string, fallback: number) =>
    value === "" ? fallback : Number(value);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1 text-xs">
          <span className="font-medium">Risk band</span>
          <Select
            items={RISK_BANDS.map((value) => ({ value, label: value }))}
            value={draft.risk_band}
            onValueChange={(value) =>
              setDraft({
                ...draft,
                risk_band: value as Profile["risk_band"],
              })
            }
          >
            <SelectTrigger aria-label="Risk band" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RISK_BANDS.map((value) => (
                <SelectItem key={value} value={value}>
                  {value}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <label className="space-y-1 text-xs">
          <span className="font-medium">Position cap (%)</span>
          <Input
            type="number"
            min={0}
            max={100}
            value={draft.position_cap_pct}
            onChange={(event) =>
              setDraft({
                ...draft,
                position_cap_pct: numberValue(event.target.value, draft.position_cap_pct),
              })
            }
          />
        </label>
        <div className="space-y-1 text-xs">
          <span className="font-medium">Horizon</span>
          <Select
            items={HORIZONS.map((value) => ({ value, label: value }))}
            value={draft.horizon}
            onValueChange={(value) =>
              setDraft({ ...draft, horizon: value as Profile["horizon"] })
            }
          >
            <SelectTrigger aria-label="Horizon" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {HORIZONS.map((value) => (
                <SelectItem key={value} value={value}>
                  {value}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <label className="space-y-1 text-xs">
          <span className="font-medium">Max notional per ticket</span>
          <Input
            type="number"
            min={0}
            value={draft.execution.max_order_notional}
            onChange={(event) =>
              setDraft({
                ...draft,
                execution: {
                  ...draft.execution,
                  max_order_notional: numberValue(
                    event.target.value,
                    draft.execution.max_order_notional,
                  ),
                },
              })
            }
          />
        </label>
      </div>

      <label className="block space-y-1 text-xs">
        <span className="font-medium">Sector exclusions</span>
        <Input
          value={exclusionsText}
          placeholder="Energy, Utilities"
          onChange={(event) => setExclusionsText(event.target.value)}
        />
      </label>

      <label className="block space-y-1 text-xs">
        <span className="font-medium">Watchlist</span>
        <Input
          value={watchlistText}
          placeholder="NVDA, MSFT"
          onChange={(event) => setWatchlistText(event.target.value)}
        />
      </label>

      <label className="block space-y-1 text-xs">
        <span className="font-medium">Source preferences</span>
        <Input
          value={sourcesText}
          placeholder="sec_edgar, finnhub"
          onChange={(event) => setSourcesText(event.target.value)}
        />
      </label>

      <div className="flex items-center justify-between rounded-lg border px-3 py-2">
        <div>
          <p className="text-xs font-medium">Autonomous execution</p>
          <p className="text-[10px] text-muted-foreground">
            Orders still pass the constraint check.
          </p>
        </div>
        <Switch
          checked={draft.execution.autonomous}
          onCheckedChange={(checked) =>
            setDraft({
              ...draft,
              execution: { ...draft.execution, autonomous: checked },
            })
          }
        />
      </div>

      <div className="flex justify-end">
        <Button onClick={submit} disabled={saving}>
          Save profile
        </Button>
      </div>

      <AlertDialog
        open={pending !== null}
        onOpenChange={(open) => !open && setPending(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Change a hard constraint?</AlertDialogTitle>
            <AlertDialogDescription>
              This changes what the agent is allowed to do. The next order uses the new
              values.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => pending && void save(pending)}>
              Save changes
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/**
 * Profile destination dialog.
 *
 * @param props - Open state.
 * @returns The dialog.
 */
export function ProfileDialog({ open, onOpenChange }: DialogProps) {
  const { data, error, loading } = useResource(() => getProfile(), open);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] w-[min(560px,100vw-32px)] max-w-none overflow-y-auto sm:max-w-none">
        <DialogHeader>
          <DialogTitle>Profile</DialogTitle>
          <DialogDescription>
            Risk, constraints, and execution permissions.
          </DialogDescription>
        </DialogHeader>
        {loading ? <Skeleton className="h-72 w-full" /> : null}
        {error ? <p className="text-sm text-muted-foreground">{error}</p> : null}
        {data ? <ProfileForm key={data.updated_at} profile={data} /> : null}
      </DialogContent>
    </Dialog>
  );
}
