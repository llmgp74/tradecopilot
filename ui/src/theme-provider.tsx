import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/** Persisted preference key shared by the provider and the appearance control. */
export const THEME_STORAGE_KEY = "tradecopilot-theme";

/** Theme value the UI renders against. */
export type Theme = "light" | "dark";

/** User preference: a fixed theme or the operating system setting. */
export type ThemePreference = Theme | "system";

interface ThemeContextValue {
  /** Resolved theme, never `system`. */
  theme: Theme;
  /** Stored preference. */
  preference: ThemePreference;
  /** Sets and persists the preference. */
  setPreference: (preference: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

/**
 * Reads the stored preference, defaulting to the system setting.
 *
 * @returns The initial preference.
 */
function readInitialPreference(): ThemePreference {
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  if (stored === "light" || stored === "dark" || stored === "system") {
    return stored;
  }
  return "system";
}

/**
 * Reports the current operating system color scheme.
 *
 * @returns `dark` when the system prefers a dark scheme.
 */
function readSystemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * Applies the theme class and provides the preference to descendants.
 *
 * @param props - Provider props.
 * @param props.children - Application tree.
 * @returns The themed tree.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] =
    useState<ThemePreference>(readInitialPreference);
  const [systemTheme, setSystemTheme] = useState<Theme>(readSystemTheme);

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent) => {
      setSystemTheme(event.matches ? "dark" : "light");
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const theme: Theme = preference === "system" ? systemTheme : preference;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  const setPreference = useCallback((next: ThemePreference) => {
    localStorage.setItem(THEME_STORAGE_KEY, next);
    setPreferenceState(next);
  }, []);

  const value = useMemo(
    () => ({ theme, preference, setPreference }),
    [theme, preference, setPreference],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

/**
 * Returns the resolved theme, the stored preference, and a setter.
 *
 * @returns The current theme state.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (value === null) {
    throw new Error("useTheme must be used inside ThemeProvider.");
  }
  return value;
}
