import { ChevronDownIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { AppSettings } from "@/lib/api";
import { ProviderIcon } from "@/components/provider-icon";

/** Props for the composer model selector. */
export interface ModelSelectorProps {
  /** Effective settings with the configured providers and models. */
  settings: AppSettings;
  /** Selected catalog provider id. */
  provider: string;
  /** Selected catalog model id. */
  modelId: string;
  /** Disabled while a turn streams. */
  disabled: boolean;
  /** Receives the chosen provider and model. */
  onChange: (provider: string, modelId: string) => void;
  /** Opens Settings on the model providers section. */
  onManage: () => void;
}

/**
 * Renders the composer trigger and the menu of configured models.
 *
 * The menu is built from settings only. The catalog is never loaded here.
 *
 * @param props - Selection, settings, and callbacks.
 * @returns The selector.
 */
export function ModelSelector({
  settings,
  provider,
  modelId,
  disabled,
  onChange,
  onManage,
}: ModelSelectorProps) {
  const providers = settings.providers.filter((item) => item.models.length > 0);
  const selected = providers
    .find((item) => item.provider_id === provider)
    ?.models.find((item) => item.id === modelId);
  const label = selected?.name ?? (modelId === "" ? "Set model" : modelId);
  const value = provider !== "" && modelId !== "" ? `${provider}:${modelId}` : "";

  const choose = (next: string) => {
    const separator = next.indexOf(":");
    if (separator < 0) {
      return;
    }
    onChange(next.slice(0, separator), next.slice(separator + 1));
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled}
            className="max-w-56 gap-1 text-xs"
          />
        }
      >
        <span className="truncate">{label}</span>
        <ChevronDownIcon className="size-3.5 shrink-0 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-56">
        {providers.length === 0 ? (
          <DropdownMenuItem onClick={onManage}>No models configured</DropdownMenuItem>
        ) : (
          <DropdownMenuRadioGroup value={value} onValueChange={choose}>
            {providers.map((item) => (
              <DropdownMenuGroup key={item.provider_id}>
                <DropdownMenuLabel className="flex items-center gap-1.5">
                  <ProviderIcon provider={item.provider_id} />
                  {item.provider_id}
                </DropdownMenuLabel>
                {item.models.map((model) => (
                  <DropdownMenuRadioItem
                    key={model.id}
                    value={`${item.provider_id}:${model.id}`}
                  >
                    {model.name}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuGroup>
            ))}
          </DropdownMenuRadioGroup>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onManage}>Manage models</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
