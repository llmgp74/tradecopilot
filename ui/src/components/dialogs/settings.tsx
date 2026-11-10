import { useEffect, useState } from "react";
import { EyeIcon, EyeOffIcon } from "lucide-react";
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
import { getSettings, patchSettings, type AppSettings } from "@/lib/api";
import { SECRET_FIELDS, settingsChanges } from "@/lib/settings";
import { useResource } from "@/lib/use-resource";
import { useTheme, type ThemePreference } from "@/theme-provider";
import type { DialogProps } from "./portfolio";

interface SettingField {
  key: keyof Omit<AppSettings, "updated_at">;
  label: string;
  placeholder?: string;
}

const THEME_OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

const GROUPS: { title: string; fields: SettingField[] }[] = [
  {
    title: "Model",
    fields: [
      { key: "agent_model", label: "Provider and model", placeholder: "provider:model" },
      { key: "model_api_key", label: "Model API key" },
    ],
  },
  {
    title: "Broker",
    fields: [
      { key: "alpaca_api_key", label: "Alpaca key" },
      { key: "alpaca_api_secret", label: "Alpaca secret" },
      {
        key: "alpaca_base_url",
        label: "Alpaca base URL",
        placeholder: "https://paper-api.alpaca.markets",
      },
    ],
  },
  {
    title: "Web search",
    fields: [{ key: "exa_api_key", label: "Exa API key" }],
  },
  {
    title: "Data providers",
    fields: [
      { key: "fmp_api_key", label: "FMP API key" },
      { key: "finnhub_api_key", label: "Finnhub API key" },
      { key: "fred_api_key", label: "FRED API key" },
      {
        key: "edgar_user_agent",
        label: "EDGAR user agent",
        placeholder: "Name you@example.com",
      },
    ],
  },
];

/**
 * Settings destination dialog.
 *
 * Every close path (X, overlay, Escape, Close) goes through one guard so a
 * form with pending edits is never discarded silently.
 *
 * @param props - Open state.
 * @returns The dialog.
 */
export function SettingsDialog({ open, onOpenChange }: DialogProps) {
  const { data, error, loading } = useResource(() => getSettings(), open);
  const { preference, setPreference } = useTheme();
  const [draft, setDraft] = useState<AppSettings | null>(null);
  const [baseline, setBaseline] = useState<AppSettings | null>(null);
  const [visibleSecrets, setVisibleSecrets] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  useEffect(() => {
    if (data !== null) {
      setDraft(data);
      setBaseline(data);
    }
  }, [data]);

  const changes = draft && baseline ? settingsChanges(baseline, draft) : {};
  const dirty = Object.keys(changes).length > 0;

  const requestClose = (next: boolean) => {
    if (!next && dirty) {
      setConfirmDiscard(true);
      return;
    }
    onOpenChange(next);
  };

  const save = async () => {
    if (!draft || !dirty) {
      return;
    }
    setSaving(true);
    try {
      const updated = await patchSettings(changes);
      setDraft(updated);
      setBaseline(updated);
      toast.success("Settings saved.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={requestClose}>
        <DialogContent className="max-h-[85vh] w-[min(640px,100vw-32px)] max-w-none overflow-y-auto sm:max-w-none">
          <DialogHeader>
            <DialogTitle>Settings</DialogTitle>
            <DialogDescription>Model, broker, and data provider keys.</DialogDescription>
          </DialogHeader>

          {loading && draft === null ? <Skeleton className="h-72 w-full" /> : null}
          {error ? <p className="text-sm text-muted-foreground">{error}</p> : null}

          {draft ? (
            <div className="space-y-5">
              <section className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Appearance
                </h3>
                <div className="flex items-center justify-between rounded-lg border px-3 py-2">
                  <div>
                    <p className="text-xs font-medium">Theme</p>
                    <p className="text-[10px] text-muted-foreground">
                      Applies to the whole app.
                    </p>
                  </div>
                  <Select
                    items={THEME_OPTIONS}
                    value={preference}
                    onValueChange={(value) => setPreference(value as ThemePreference)}
                  >
                    <SelectTrigger aria-label="Theme" className="w-36">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {THEME_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </section>

              {GROUPS.map((group) => (
                <section key={group.title} className="space-y-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {group.title}
                  </h3>
                  {group.fields.map((field) => {
                    const secret = SECRET_FIELDS.has(field.key);
                    const visible = visibleSecrets.has(field.key);
                    return (
                      <label key={field.key} className="block space-y-1 text-xs">
                        <span className="font-medium">{field.label}</span>
                        {secret ? (
                          <div className="relative">
                            <Input
                              type={visible ? "text" : "password"}
                              value={draft[field.key]}
                              onChange={(event) =>
                                setDraft({ ...draft, [field.key]: event.target.value })
                              }
                              placeholder={field.placeholder}
                              className="pr-9"
                            />
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon-sm"
                              className="absolute inset-y-0 right-1 my-auto"
                              aria-label={
                                visible ? `Hide ${field.label}` : `Show ${field.label}`
                              }
                              onClick={() =>
                                setVisibleSecrets((current) => {
                                  const next = new Set(current);
                                  if (next.has(field.key)) {
                                    next.delete(field.key);
                                  } else {
                                    next.add(field.key);
                                  }
                                  return next;
                                })
                              }
                            >
                              {visible ? (
                                <EyeOffIcon className="size-3.5" />
                              ) : (
                                <EyeIcon className="size-3.5" />
                              )}
                            </Button>
                          </div>
                        ) : (
                          <Input
                            value={draft[field.key]}
                            onChange={(event) =>
                              setDraft({ ...draft, [field.key]: event.target.value })
                            }
                            placeholder={field.placeholder}
                          />
                        )}
                      </label>
                    );
                  })}
                </section>
              ))}

              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => requestClose(false)}>
                  Close
                </Button>
                <Button onClick={() => void save()} disabled={!dirty || saving}>
                  Save settings
                </Button>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      <AlertDialog open={confirmDiscard} onOpenChange={setConfirmDiscard}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Discard unsaved changes?</AlertDialogTitle>
            <AlertDialogDescription>
              The form has pending edits that will be lost.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep editing</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setConfirmDiscard(false);
                onOpenChange(false);
              }}
            >
              Discard
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
