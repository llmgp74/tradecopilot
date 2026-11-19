import { useCallback, useEffect, useMemo, useState } from "react";
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
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  deleteProvider,
  patchSettings,
  putProvider,
  type AppSettings,
  type ProviderModel,
} from "@/lib/api";
import { loadModelCatalog, SUPPORTED_NPM, type ModelCatalog } from "@/lib/catalog";
import { reasoningChoices } from "@/lib/reasoning";
import { ProviderIcon } from "@/components/provider-icon";
import { AddModelsDialog } from "./add-models-dialog";

/** Props for the model providers section. */
export interface ModelProvidersSectionProps {
  /** Effective settings. */
  settings: AppSettings;
  /** Receives settings after a save. */
  onSaved: (settings: AppSettings) => void;
  /** Reports unsaved edits to the dialog. */
  onDirtyChange: (dirty: boolean) => void;
}

interface ProviderDraft {
  providerId: string;
  apiKey: string;
  baseUrl: string;
  npm: string;
  models: ProviderModel[];
}

interface ProviderRow {
  id: string;
  name: string;
  configured: boolean;
  supported: boolean;
  hasKey: boolean;
  modelCount: number;
}

/**
 * Builds a draft from a stored credential or a catalog entry.
 *
 * @param providerId - Catalog provider id.
 * @param settings - Effective settings.
 * @param catalog - Loaded catalog, when available.
 * @returns The draft.
 */
function draftFor(
  providerId: string,
  settings: AppSettings,
  catalog: ModelCatalog | null,
): ProviderDraft {
  const stored = settings.providers.find((item) => item.provider_id === providerId);
  const entry = catalog?.providers[providerId];
  return {
    providerId,
    apiKey: stored?.api_key ?? "",
    baseUrl: stored?.base_url ?? entry?.api ?? "",
    npm: stored?.npm ?? entry?.npm ?? "",
    models: stored?.models ?? [],
  };
}

/**
 * Reports whether a draft differs from the stored row. A new empty draft is
 * not dirty, so selecting a provider does not trip the discard guard.
 *
 * @param draft - Current draft.
 * @param settings - Effective settings.
 * @returns True when there are unsaved edits.
 */
function isDirty(draft: ProviderDraft, settings: AppSettings): boolean {
  const stored = settings.providers.find((item) => item.provider_id === draft.providerId);
  if (stored === undefined) {
    return draft.apiKey !== "" || draft.models.length > 0;
  }
  return (
    draft.apiKey !== stored.api_key ||
    draft.baseUrl !== stored.base_url ||
    draft.npm !== stored.npm ||
    JSON.stringify(draft.models) !== JSON.stringify(stored.models)
  );
}

/**
 * Renders the provider list, provider detail, and save actions.
 *
 * @param props - Settings and dialog callbacks.
 * @returns The section body.
 */
export function ModelProvidersSection({
  settings,
  onSaved,
  onDirtyChange,
}: ModelProvidersSectionProps) {
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<ProviderDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [removedSelected, setRemovedSelected] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [pendingSelect, setPendingSelect] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);

  const reloadCatalog = useCallback(async () => {
    setLoading(true);
    const result = await loadModelCatalog();
    setCatalog(result.catalog);
    setLoading(false);
  }, []);

  useEffect(() => {
    void reloadCatalog();
  }, [reloadCatalog]);

  const dirty = draft !== null && isDirty(draft, settings);
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  const rows = useMemo<ProviderRow[]>(() => {
    const configured = settings.providers.map((item) => ({
      id: item.provider_id,
      name: catalog?.providers[item.provider_id]?.name ?? item.provider_id,
      configured: true,
      supported: SUPPORTED_NPM.has(item.npm),
      hasKey: item.api_key !== "",
      modelCount: item.models.length,
    }));
    const configuredIds = new Set(configured.map((row) => row.id));
    const others = Object.entries(catalog?.providers ?? {})
      .filter(([id]) => !configuredIds.has(id))
      .map(([id, entry]) => ({
        id,
        name: entry.name,
        configured: false,
        supported: SUPPORTED_NPM.has(entry.npm),
        hasKey: false,
        modelCount: Object.keys(entry.models).length,
      }));
    const needle = search.trim().toLowerCase();
    return [...configured, ...others].filter((row) => {
      if (needle === "") {
        return true;
      }
      return (
        row.name.toLowerCase().includes(needle) || row.id.toLowerCase().includes(needle)
      );
    });
  }, [settings.providers, catalog, search]);

  const select = (providerId: string) => {
    setSelected(providerId);
    setDraft(draftFor(providerId, settings, catalog));
    setRemovedSelected(false);
    setSearch("");
  };

  const requestSelect = (providerId: string) => {
    if (dirty) {
      setPendingSelect(providerId);
      return;
    }
    select(providerId);
  };

  const save = async () => {
    if (!draft) {
      return;
    }
    setSaving(true);
    try {
      const updated = await putProvider(draft.providerId, {
        api_key: draft.apiKey,
        base_url: draft.baseUrl,
        npm: draft.npm,
        models: draft.models,
      });
      setDraft(draftFor(draft.providerId, updated, catalog));
      setRemovedSelected(false);
      onSaved(updated);
      toast.success("Provider saved.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  const clear = async () => {
    if (!draft) {
      return;
    }
    try {
      const updated = await deleteProvider(draft.providerId);
      onSaved(updated);
      setSelected(null);
      setDraft(null);
      setConfirmClear(false);
      toast.success("Provider removed.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Delete failed.");
    }
  };

  const removeModel = (model: ProviderModel) => {
    if (!draft) {
      return;
    }
    setDraft({
      ...draft,
      models: draft.models.filter((item) => item.id !== model.id),
    });
    if (model.id === settings.model_id) {
      setRemovedSelected(true);
    }
  };

  const detailName =
    selected === null ? "" : (catalog?.providers[selected]?.name ?? selected);

  const selectedModel = settings.providers
    .find((item) => item.provider_id === settings.model_provider)
    ?.models.find((item) => item.id === settings.model_id);
  const reasoning = reasoningChoices(selectedModel?.reasoning_options ?? []);

  const setDefaultReasoning = async (value: string) => {
    try {
      const updated = await patchSettings({
        reasoning_effort: value === "default" ? "" : value,
      });
      onSaved(updated);
      toast.success("Default reasoning saved.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Save failed.");
    }
  };

  return (
    <div className="flex h-full min-h-0 gap-4">
      <div className="flex w-60 shrink-0 flex-col gap-2">
        <div className="space-y-2">
          <label
            htmlFor="default-reasoning"
            className="text-[10px] font-medium text-muted-foreground"
          >
            Default reasoning
          </label>
          <Select
            items={[{ value: "default", label: "Default" }, ...reasoning]}
            value={settings.reasoning_effort || "default"}
            onValueChange={(value) => {
              if (value !== null) {
                void setDefaultReasoning(value);
              }
            }}
            disabled={reasoning.length === 0}
          >
            <SelectTrigger
              id="default-reasoning"
              aria-label="Default reasoning"
              className="w-full"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="default">Default</SelectItem>
              {reasoning.map((choice) => (
                <SelectItem key={choice.value} value={choice.value}>
                  {choice.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Input
          aria-label="Search providers"
          placeholder="Search providers"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
          {loading ? <Skeleton className="h-24 w-full" /> : null}
          {rows.map((row) => (
            <button
              key={row.id}
              type="button"
              disabled={!row.supported}
              aria-current={row.id === selected ? "page" : undefined}
              onClick={() => requestSelect(row.id)}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50 aria-current:bg-accent aria-current:font-medium"
            >
              <ProviderIcon provider={row.id} />
              <span className="min-w-0 flex-1 truncate">{row.name}</span>
              {!row.supported ? (
                <span aria-hidden className="text-[10px] text-muted-foreground">
                  Not supported
                </span>
              ) : null}
              {row.hasKey ? (
                <span
                  aria-hidden
                  data-testid={`provider-status-${row.id}`}
                  className="size-1.5 shrink-0 rounded-full"
                  style={{
                    background:
                      row.modelCount > 0 ? "var(--positive)" : "var(--muted-foreground)",
                  }}
                />
              ) : null}
            </button>
          ))}
        </div>
      </div>

      <div className="min-w-0 flex-1 space-y-4 overflow-y-auto">
        {draft === null ? (
          <p className="text-sm text-muted-foreground">
            Select a provider to edit its key and models.
          </p>
        ) : (
          <>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <ProviderIcon provider={selected ?? ""} className="size-4" />
                <h3 className="text-sm font-semibold">{detailName}</h3>
              </div>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setConfirmClear(true)}
                >
                  Clear provider
                </Button>
                <Button
                  type="button"
                  size="sm"
                  onClick={() => void save()}
                  disabled={!dirty || saving}
                >
                  Save provider
                </Button>
              </div>
            </div>

            <div className="space-y-2 text-xs">
              <label htmlFor="provider-api-key" className="font-medium">
                API key
              </label>
              <Input
                id="provider-api-key"
                type="password"
                value={draft.apiKey}
                onChange={(event) => setDraft({ ...draft, apiKey: event.target.value })}
              />
            </div>

            <div className="space-y-2 text-xs">
              <label htmlFor="provider-base-url" className="font-medium">
                Base URL
              </label>
              <Input
                id="provider-base-url"
                value={draft.baseUrl}
                onChange={(event) => setDraft({ ...draft, baseUrl: event.target.value })}
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Models
                </h4>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={selected === null || !catalog?.providers[selected]}
                  onClick={() => setAddOpen(true)}
                >
                  Add models
                </Button>
              </div>
              {removedSelected ? (
                <p className="text-xs" style={{ color: "var(--warning)" }}>
                  Saving changes the selection.
                </p>
              ) : null}
              {draft.models.length === 0 ? (
                <p className="text-xs text-muted-foreground">No models selected.</p>
              ) : (
                draft.models.map((model) => (
                  <div
                    key={model.id}
                    className="flex items-center gap-2 rounded-lg border px-3 py-2"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium">{model.name}</p>
                      <p className="truncate font-mono text-[10px] text-muted-foreground">
                        {model.id}
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove ${model.name}`}
                      onClick={() => removeModel(model)}
                    >
                      Remove
                    </Button>
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </div>

      <AddModelsDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        providerName={detailName}
        models={catalog?.providers[selected ?? ""]?.models ?? {}}
        addedIds={draft?.models.map((model) => model.id) ?? []}
        onAdd={(models) =>
          setDraft((current) =>
            current === null
              ? current
              : { ...current, models: [...current.models, ...models] },
          )
        }
      />

      <AlertDialog open={confirmClear} onOpenChange={setConfirmClear}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this provider?</AlertDialogTitle>
            <AlertDialogDescription>
              Its key and configured models are deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep</AlertDialogCancel>
            <AlertDialogAction onClick={() => void clear()}>Remove</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={pendingSelect !== null}
        onOpenChange={(next) => !next && setPendingSelect(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Discard unsaved changes?</AlertDialogTitle>
            <AlertDialogDescription>
              The provider form has pending edits that will be lost.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep editing</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pendingSelect !== null) {
                  select(pendingSelect);
                }
                setPendingSelect(null);
              }}
            >
              Discard
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
