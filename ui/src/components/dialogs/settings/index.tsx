import { useEffect, useState } from "react";
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
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { getSettings, type AppSettings } from "@/lib/api";
import { useResource } from "@/lib/use-resource";
import type { SettingsSection } from "@/lib/settings";
import type { DialogProps } from "../portfolio";
import { ModelProvidersSection } from "./model-providers";
import { GeneralSection, SettingsFieldSection, type SettingField } from "./sections";

const SECTIONS: { value: SettingsSection; label: string }[] = [
  { value: "general", label: "General" },
  { value: "models", label: "Model Providers" },
  { value: "broker", label: "Broker" },
  { value: "search", label: "Web Search" },
  { value: "data", label: "Data Providers" },
];

const SECTION_FIELDS: Record<
  Exclude<SettingsSection, "general" | "models">,
  SettingField[]
> = {
  broker: [
    { key: "alpaca_api_key", label: "Alpaca key" },
    { key: "alpaca_api_secret", label: "Alpaca secret" },
    {
      key: "alpaca_base_url",
      label: "Alpaca base URL",
      defaultValue: "https://paper-api.alpaca.markets/v2",
    },
  ],
  search: [{ key: "exa_api_key", label: "Exa API key" }],
  data: [
    { key: "fmp_api_key", label: "FMP API key" },
    { key: "finnhub_api_key", label: "Finnhub API key" },
    { key: "fred_api_key", label: "FRED API key" },
    {
      key: "edgar_user_agent",
      label: "EDGAR user agent",
      placeholder: "Name you@example.com",
    },
  ],
};

type PendingSwitch = { kind: "close" } | { kind: "section"; next: SettingsSection };

/** Props for the settings dialog. */
export interface SettingsDialogProps extends DialogProps {
  /** Section shown when the dialog opens. */
  initialSection?: SettingsSection;
}

/**
 * Settings sheet with a section list and one content pane.
 *
 * Every close path and section switch goes through the dirty guard so a draft
 * is never discarded silently.
 *
 * @param props - Open state and the initial section.
 * @returns The dialog.
 */
export function SettingsDialog({
  open,
  onOpenChange,
  initialSection = "general",
}: SettingsDialogProps) {
  const { data, error, loading, reload } = useResource(() => getSettings(), open);
  const [section, setSection] = useState<SettingsSection>(initialSection);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState<PendingSwitch | null>(null);

  useEffect(() => {
    if (open) {
      setSection(initialSection);
      setDirty(false);
      setPending(null);
    }
  }, [open, initialSection]);

  useEffect(() => {
    if (data !== null) {
      setSettings(data);
    }
  }, [data]);

  const requestClose = (next: boolean) => {
    if (!next && dirty) {
      setPending({ kind: "close" });
      return;
    }
    onOpenChange(next);
  };

  const requestSection = (next: SettingsSection) => {
    if (next === section) {
      return;
    }
    if (dirty) {
      setPending({ kind: "section", next });
      return;
    }
    setDirty(false);
    setSection(next);
  };

  const discard = () => {
    if (pending?.kind === "close") {
      setPending(null);
      onOpenChange(false);
      return;
    }
    if (pending?.kind === "section") {
      setDirty(false);
      setSection(pending.next);
    }
    setPending(null);
  };

  const saved = (updated: AppSettings) => {
    setSettings(updated);
    setDirty(false);
    reload();
  };

  return (
    <>
      <Dialog open={open} onOpenChange={requestClose}>
        <DialogContent className="flex h-[min(760px,85vh)] w-[min(1100px,100vw-32px)] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none">
          <DialogHeader className="border-b px-5 py-4">
            <DialogTitle>Settings</DialogTitle>
            <DialogDescription>
              Model providers, broker, and data sources.
            </DialogDescription>
          </DialogHeader>

          <div className="flex min-h-0 flex-1">
            <nav
              aria-label="Settings sections"
              className="w-[180px] shrink-0 border-r p-2"
            >
              {SECTIONS.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  aria-current={item.value === section ? "page" : undefined}
                  onClick={() => requestSection(item.value)}
                  className="mb-0.5 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-accent aria-current:bg-accent aria-current:font-medium"
                >
                  {item.label}
                  {item.value === "models" && (settings?.providers.length ?? 0) > 0 ? (
                    <Badge
                      variant="secondary"
                      aria-hidden
                      className="ml-auto h-4 px-1 text-[10px]"
                    >
                      {settings?.providers.length}
                    </Badge>
                  ) : null}
                </button>
              ))}
            </nav>

            <div className="min-w-0 flex-1 overflow-y-auto p-5">
              {loading && settings === null ? <Skeleton className="h-72 w-full" /> : null}
              {error ? <p className="text-sm text-muted-foreground">{error}</p> : null}
              {settings ? (
                section === "general" ? (
                  <GeneralSection />
                ) : section === "models" ? (
                  <ModelProvidersSection
                    settings={settings}
                    onSaved={saved}
                    onDirtyChange={setDirty}
                  />
                ) : (
                  <SettingsFieldSection
                    key={section}
                    settings={settings}
                    fields={SECTION_FIELDS[section]}
                    onSaved={saved}
                    onDirtyChange={setDirty}
                  />
                )
              ) : null}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={pending !== null}
        onOpenChange={(next) => !next && setPending(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Discard unsaved changes?</AlertDialogTitle>
            <AlertDialogDescription>
              The form has pending edits that will be lost.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep editing</AlertDialogCancel>
            <AlertDialogAction onClick={discard}>Discard</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
