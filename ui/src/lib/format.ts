/**
 * Formats a number as US dollars.
 *
 * @param value - Amount in USD.
 * @param digits - Fraction digits to show.
 * @returns The formatted currency string.
 */
export function formatUsd(value: number, digits = 2): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

/**
 * Formats percentage points.
 *
 * @param value - Percentage points.
 * @param digits - Fraction digits to show.
 * @returns The formatted percentage.
 */
export function formatPct(value: number, digits = 2): string {
  return `${value.toFixed(digits)}%`;
}

/**
 * Formats percentage points with an explicit sign for positive values.
 *
 * @param value - Percentage points.
 * @param digits - Fraction digits to show.
 * @returns The signed percentage.
 */
export function formatSignedPct(value: number, digits = 2): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}
