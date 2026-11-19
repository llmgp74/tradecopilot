import { ChevronDownIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ReasoningChoice } from "@/lib/reasoning";

/** Props for the per-turn reasoning selector. */
export interface ReasoningSelectorProps {
  /** Choices for the selected model. */
  choices: ReasoningChoice[];
  /** Current override, or null to inherit the saved default. */
  value: string | null;
  /** Disabled while a turn streams. */
  disabled: boolean;
  /** Receives the chosen level, or null for the default. */
  onChange: (value: string | null) => void;
}

/**
 * Renders the temporary reasoning menu beside the model trigger.
 *
 * @param props - Choices, current value, and callback.
 * @returns The selector.
 */
export function ReasoningSelector({
  choices,
  value,
  disabled,
  onChange,
}: ReasoningSelectorProps) {
  const selected = choices.find((choice) => choice.value === value);
  const label = value === null ? "Default" : (selected?.label ?? value);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled}
            className="max-w-32 gap-1 text-xs"
          />
        }
      >
        <span className="truncate">{label}</span>
        <ChevronDownIcon className="size-3.5 shrink-0 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-40">
        <DropdownMenuRadioGroup
          value={value ?? "default"}
          onValueChange={(next) => onChange(next === "default" ? null : next)}
        >
          <DropdownMenuRadioItem value="default">Default</DropdownMenuRadioItem>
          {choices.map((choice) => (
            <DropdownMenuRadioItem key={choice.value} value={choice.value}>
              {choice.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
