import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

interface ErrorBoundaryState {
  hasError: boolean;
}

/**
 * Keeps one render failure from blanking the whole app.
 *
 * The underlying error is still logged, and the fallback offers a way back
 * without reloading the window.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode },
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false };

  /**
   * Switches to the fallback when a descendant throws.
   *
   * @returns The failed state.
   */
  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  /**
   * Records the failure for diagnostics.
   *
   * @param error - Thrown error.
   * @param info - Component stack.
   */
  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("TradeCopilot UI error", error, info);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          className="flex h-screen flex-col items-center justify-center gap-3 bg-background p-6 text-center text-foreground"
        >
          <p className="text-sm font-medium">Something went wrong while rendering.</p>
          <p className="text-xs text-muted-foreground">
            The conversation is still stored. Try rendering it again.
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => this.setState({ hasError: false })}
          >
            Try again
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}
