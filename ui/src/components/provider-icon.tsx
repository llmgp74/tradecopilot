import { useState } from "react";
import { cn } from "@/lib/utils";

/** Props for a provider logo. */
export interface ProviderIconProps {
  /** models.dev provider id. */
  provider: string;
  /** Extra classes for size overrides. */
  className?: string;
}

/**
 * Renders a provider logo from models.dev.
 *
 * The image is decorative because the provider name sits beside it. A failed
 * load hides the image rather than showing a broken-image marker.
 *
 * @param props - Provider id and size classes.
 * @returns The logo, or null without an id.
 */
export function ProviderIcon({ provider, className }: ProviderIconProps) {
  const [failed, setFailed] = useState(false);
  if (provider === "" || failed) {
    return null;
  }
  return (
    <img
      alt=""
      aria-hidden
      height={14}
      width={14}
      src={`https://models.dev/logos/${provider}.svg`}
      className={cn("size-3.5 shrink-0 dark:invert", className)}
      onError={() => setFailed(true)}
    />
  );
}
