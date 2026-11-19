import { useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ProviderModel } from "@/lib/api";
import type { CatalogModel } from "@/lib/catalog";

/** Props for the model picker. */
export interface AddModelsDialogProps {
  /** Dialog visibility. */
  open: boolean;
  /** Visibility callback. */
  onOpenChange: (open: boolean) => void;
  /** Provider display name used in the title. */
  providerName: string;
  /** Catalog models for the provider, keyed by id. */
  models: Record<string, CatalogModel>;
  /** Ids already configured. */
  addedIds: string[];
  /** Receives the selected models. */
  onAdd: (models: ProviderModel[]) => void;
}

/**
 * Searches and selects catalog models for one provider.
 *
 * Models without tool calling and models already added are disabled.
 *
 * @param props - Open state, catalog models, and callback.
 * @returns The dialog.
 */
export function AddModelsDialog({
  open,
  onOpenChange,
  providerName,
  models,
  addedIds,
  onAdd,
}: AddModelsDialogProps) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (open) {
      setSearch("");
      setSelected(new Set());
    }
  }, [open]);

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return Object.entries(models).filter(([id, model]) => {
      if (needle === "") {
        return true;
      }
      return (
        model.name.toLowerCase().includes(needle) || id.toLowerCase().includes(needle)
      );
    });
  }, [models, search]);

  const toggle = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const add = () => {
    const chosen = Object.entries(models)
      .filter(([id]) => selected.has(id))
      .map(([id, model]) => ({
        id,
        name: model.name,
        tool_call: model.tool_call,
        reasoning_options: model.reasoning_options,
      }));
    onAdd(chosen);
    onOpenChange(false);
  };

  const count = selected.size;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[min(620px,80vh)] w-[min(560px,100vw-32px)] max-w-none flex-col gap-0 p-0 sm:max-w-none">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle>Add models to {providerName}</DialogTitle>
          <DialogDescription>
            Only models that support tool calls can be added.
          </DialogDescription>
        </DialogHeader>

        <div className="border-b px-4 py-3">
          <Input
            aria-label="Search models"
            placeholder="Search models"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>

        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto px-4 py-3">
          {rows.length === 0 ? (
            <p className="py-6 text-center text-xs text-muted-foreground">
              No models match.
            </p>
          ) : (
            rows.map(([id, model]) => {
              const added = addedIds.includes(id);
              const disabled = added || !model.tool_call;
              return (
                <label
                  key={id}
                  className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-1.5 text-xs hover:bg-accent has-disabled:cursor-not-allowed has-disabled:opacity-60"
                >
                  <input
                    type="checkbox"
                    className="size-4 accent-primary"
                    aria-label={model.name}
                    checked={selected.has(id)}
                    disabled={disabled}
                    onChange={() => toggle(id)}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{model.name}</span>
                    <span className="block truncate font-mono text-[10px] text-muted-foreground">
                      {id}
                    </span>
                  </span>
                  {added ? (
                    <span className="text-[10px] text-muted-foreground">
                      Already added
                    </span>
                  ) : !model.tool_call ? (
                    <span className="text-[10px] text-muted-foreground">
                      No tool support
                    </span>
                  ) : null}
                </label>
              );
            })
          )}
        </div>

        <div className="flex justify-end gap-2 border-t px-4 py-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={add} disabled={count === 0}>
            Add {count === 0 ? "models" : `${count} ${count === 1 ? "model" : "models"}`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
