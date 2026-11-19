import { useState } from "react";
import { ArrowUpRightIcon } from "lucide-react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getPortfolio, type Portfolio, type PortfolioRange } from "@/lib/api";
import { openExternal } from "@/lib/external";
import { formatPct, formatSignedPct, formatUsd } from "@/lib/format";
import { useResource } from "@/lib/use-resource";

/** Props shared by every destination dialog. */
export interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const RANGES: PortfolioRange[] = ["1D", "1W", "1M", "3M", "1Y", "ALL"];

const ALPACA_DASHBOARD = "https://app.alpaca.markets/dashboard/";

/** Holdings shown before the rest move to Alpaca. */
const VISIBLE_POSITIONS = 5;

const chartConfig = {
  equity: { label: "Equity", color: "var(--chart-1)" },
} satisfies ChartConfig;

/** Formats an axis amount without cents, so close ticks stay distinct. */
function axisUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

/** Formats one equity-curve timestamp for the x axis. */
function timeTick(value: string, range: PortfolioRange): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return range === "1D"
    ? date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
    : date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Formats the tooltip timestamp with more context than the axis tick. */
function timeLabel(value: string, range: PortfolioRange): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(
    "en-US",
    range === "1D"
      ? {
          month: "short",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
        }
      : { year: "numeric", month: "short", day: "numeric" },
  );
}

/**
 * Renders account metrics, the equity curve, and positions.
 *
 * @param props - Range, settings callback, and portfolio data.
 * @returns The dialog body.
 */
function PortfolioBody({
  portfolio,
  range,
  onOpenSettings,
}: {
  portfolio: Portfolio;
  range: PortfolioRange;
  onOpenSettings: () => void;
}) {
  const { account, day, positions, equity_curve } = portfolio;
  const sorted = [...positions].sort((a, b) => b.market_value - a.market_value);
  const shown = sorted.slice(0, VISIBLE_POSITIONS);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: "Equity", value: formatUsd(account.equity), detail: null },
          { label: "Cash", value: formatUsd(account.cash), detail: null },
          {
            label: "Day P&L",
            value: formatSignedPct(day.pnl_pct),
            detail: formatUsd(day.pnl),
          },
        ].map((tile) => (
          <div key={tile.label} className="rounded-lg border px-3 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              {tile.label}
            </p>
            <p className="mt-0.5 font-mono text-sm font-semibold">{tile.value}</p>
            {tile.detail ? (
              <p className="text-[10px] text-muted-foreground">{tile.detail}</p>
            ) : null}
          </div>
        ))}
      </div>

      {equity_curve.length > 0 ? (
        <ChartContainer config={chartConfig} className="h-44 w-full">
          <AreaChart
            data={equity_curve}
            margin={{ left: 0, right: 8, top: 4, bottom: 0 }}
          >
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="t"
              tickLine={false}
              axisLine={false}
              minTickGap={32}
              tickFormatter={(value) => timeTick(String(value), range)}
            />
            <YAxis
              width={84}
              tickLine={false}
              axisLine={false}
              domain={["auto", "auto"]}
              tickFormatter={(value) => axisUsd(Number(value))}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  labelFormatter={(value) => timeLabel(String(value), range)}
                  formatter={(value) => formatUsd(Number(value))}
                />
              }
            />
            <Area
              dataKey="equity"
              type="monotone"
              fill="var(--color-equity)"
              stroke="var(--color-equity)"
              fillOpacity={0.15}
              strokeWidth={1.5}
            />
          </AreaChart>
        </ChartContainer>
      ) : (
        <p className="py-6 text-center text-xs text-muted-foreground">
          No equity history for this range.
        </p>
      )}

      {sorted.length === 0 ? (
        <div className="rounded-lg border border-dashed px-4 py-8 text-center text-sm">
          <p className="text-muted-foreground">No open positions.</p>
          <Button variant="outline" size="sm" className="mt-2" onClick={onOpenSettings}>
            Open settings
          </Button>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                {[
                  "Ticker",
                  "Sector",
                  "Qty",
                  "Avg entry",
                  "Price",
                  "Value",
                  "P&L",
                  "Weight",
                ].map((heading) => (
                  <TableHead
                    key={heading}
                    className={
                      heading === "Ticker" || heading === "Sector" ? "" : "text-right"
                    }
                  >
                    {heading}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((position) => (
                <TableRow key={position.ticker}>
                  <TableCell className="font-mono font-semibold">
                    {position.ticker}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {position.sector ?? "-"}
                  </TableCell>
                  <TableCell className="text-right font-mono">{position.qty}</TableCell>
                  <TableCell className="text-right font-mono">
                    {formatUsd(position.avg_entry_price)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {formatUsd(position.current_price)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {formatUsd(position.market_value)}
                  </TableCell>
                  <TableCell
                    className="text-right font-mono"
                    style={{
                      color:
                        position.unrealized_pl >= 0
                          ? "var(--positive)"
                          : "var(--negative)",
                    }}
                  >
                    {formatSignedPct(position.unrealized_pl_pct)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {formatPct(position.weight_pct)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {sorted.length > VISIBLE_POSITIONS ? (
        <p className="text-xs text-muted-foreground">
          Showing the {VISIBLE_POSITIONS} largest of {sorted.length} holdings.
        </p>
      ) : null}
    </div>
  );
}

/**
 * Loads one range and renders it. Remounted when the range changes.
 *
 * @param props - Range and settings callback.
 * @returns The dialog body or its loading and error states.
 */
function PortfolioRangeBody({
  range,
  onOpenSettings,
}: {
  range: PortfolioRange;
  onOpenSettings: () => void;
}) {
  const { data, error, errorStatus, loading } = useResource(() => getPortfolio(range));

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-44 w-full" />
        <Skeleton className="h-28 w-full" />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="rounded-lg border border-dashed px-4 py-10 text-center text-sm">
        <p>{errorStatus === 503 ? "Broker is not configured." : error}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={onOpenSettings}>
          Open settings
        </Button>
      </div>
    );
  }
  return <PortfolioBody portfolio={data} range={range} onOpenSettings={onOpenSettings} />;
}

/**
 * Portfolio destination dialog.
 *
 * @param props - Open state and optional settings callback.
 * @returns The dialog.
 */
export function PortfolioDialog({
  open,
  onOpenChange,
  onOpenSettings,
}: DialogProps & { onOpenSettings?: () => void }) {
  const [range, setRange] = useState<PortfolioRange>("1M");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] w-[min(960px,100vw-32px)] max-w-none overflow-y-auto sm:max-w-none">
        <DialogHeader>
          <DialogTitle>Portfolio</DialogTitle>
          <DialogDescription>
            Account, positions, and equity history.{" "}
            <a
              href={ALPACA_DASHBOARD}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-medium text-link underline underline-offset-4"
              onClick={(event) => {
                event.preventDefault();
                void openExternal(ALPACA_DASHBOARD);
              }}
            >
              View in Alpaca
              <ArrowUpRightIcon className="size-3.5" aria-hidden="true" />
            </a>
          </DialogDescription>
        </DialogHeader>
        <div className="flex gap-1">
          {RANGES.map((value) => (
            <Button
              key={value}
              size="sm"
              variant={value === range ? "secondary" : "ghost"}
              onClick={() => setRange(value)}
            >
              {value}
            </Button>
          ))}
        </div>
        {open ? (
          <PortfolioRangeBody
            key={range}
            range={range}
            onOpenSettings={onOpenSettings ?? (() => {})}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
