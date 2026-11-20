import { useEffect, useId, useState } from "react";
import { EyeIcon, EyeOffIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { patchSettings, type AppSettings } from "@/lib/api";
import { SECRET_FIELDS, settingsChanges } from "@/lib/settings";
import { useTheme, type ThemePreference } from "@/theme-provider";

/** Scalar settings rendered by the field section. */
type SettingFieldKey = keyof Omit<
  AppSettings,
  "updated_at" | "providers" | "tool_permissions"
>;

/** One editable field in a non-model section. */
export interface SettingField {
  key: SettingFieldKey;
  label: string;
  placeholder?: string;
  /** Shown when the stored value is empty, so the field is never blank. */
  defaultValue?: string;
}

const THEME_OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

/**
 * Renders the theme control. It applies immediately and never marks the
 * dialog dirty.
 */
export function GeneralSection() {
  const { preference, setPreference } = useTheme();
  return (
    <div className="flex items-center justify-between rounded-lg border px-3 py-2">
      <div>
        <p className="text-xs font-medium">Theme</p>
        <p className="text-[10px] text-muted-foreground">Applies to the whole app.</p>
      </div>
      <Select
        items={THEME_OPTIONS}
        value={preference}
        onValueChange={(value) => setPreference(value as ThemePreference)}
      >
        <SelectTrigger aria-label="Theme" className="w-36">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {THEME_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/** Props for a field section. */
export interface SettingsFieldSectionProps {
  /** Effective settings. */
  settings: AppSettings;
  /** Fields to render. */
  fields: SettingField[];
  /** Receives the settings after a save. */
  onSaved: (settings: AppSettings) => void;
  /** Reports unsaved edits to the dialog. */
  onDirtyChange: (dirty: boolean) => void;
}

/**
 * Renders labelled fields with one save action for the section.
 *
 * @param props - Fields and dialog callbacks.
 * @returns The section body.
 */
export function SettingsFieldSection({
  settings,
  fields,
  onSaved,
  onDirtyChange,
}: SettingsFieldSectionProps) {
  const [draft, setDraft] = useState(settings);
  const [visible, setVisible] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const baseId = useId();

  useEffect(() => {
    setDraft(settings);
  }, [settings]);

  const changes = settingsChanges(settings, draft);
  const dirty = Object.keys(changes).length > 0;

  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  const save = async () => {
    if (!dirty) {
      return;
    }
    setSaving(true);
    try {
      const updated = await patchSettings(changes);
      setDraft(updated);
      onSaved(updated);
      toast.success("Settings saved.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {fields.map((field) => {
        const secret = SECRET_FIELDS.has(field.key);
        const revealed = visible.has(field.key);
        const inputId = `${baseId}-${field.key}`;
        return (
          <div key={field.key} className="space-y-2 text-xs">
            <label htmlFor={inputId} className="font-medium">
              {field.label}
            </label>
            {secret ? (
              <div className="relative">
                <Input
                  id={inputId}
                  type={revealed ? "text" : "password"}
                  value={draft[field.key] || field.defaultValue}
                  onChange={(event) =>
                    setDraft({ ...draft, [field.key]: event.target.value })
                  }
                  placeholder={field.placeholder}
                  className="pr-9"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="absolute inset-y-0 right-1 my-auto"
                  aria-label={revealed ? `Hide ${field.label}` : `Show ${field.label}`}
                  onClick={() =>
                    setVisible((current) => {
                      const next = new Set(current);
                      if (next.has(field.key)) {
                        next.delete(field.key);
                      } else {
                        next.add(field.key);
                      }
                      return next;
                    })
                  }
                >
                  {revealed ? (
                    <EyeOffIcon className="size-3.5" />
                  ) : (
                    <EyeIcon className="size-3.5" />
                  )}
                </Button>
              </div>
            ) : (
              <Input
                id={inputId}
                value={draft[field.key] || field.defaultValue}
                onChange={(event) =>
                  setDraft({ ...draft, [field.key]: event.target.value })
                }
                placeholder={field.placeholder}
              />
            )}
          </div>
        );
      })}
      <div className="flex justify-end">
        <Button onClick={() => void save()} disabled={!dirty || saving}>
          Save section
        </Button>
      </div>
    </div>
  );
}

/** One tool with its policy control. */
const TOOL_ROWS = [
  {
    tool: "execute",
    label: "Shell commands",
    description: "Run commands in the workspace. Commands are not sandboxed.",
  },
  {
    tool: "write_file",
    label: "Write files",
    description: "Create files. Confined to the workspace.",
  },
  {
    tool: "edit_file",
    label: "Edit files",
    description: "Modify files. Confined to the workspace.",
  },
  {
    tool: "delete",
    label: "Delete files",
    description: "Delete files. Confined to the workspace.",
  },
] as const;

/** Policies shown for each tool. */
const POLICY_OPTIONS = [
  { value: "ask", label: "Ask" },
  { value: "auto", label: "Auto" },
];

/** Props for the permissions section. */
export interface PermissionsSectionProps {
  /** Effective settings. */
  settings: AppSettings;
  /** Receives the settings after a save. */
  onSaved: (settings: AppSettings) => void;
}

/**
 * Renders one approval policy per tool. A change applies immediately.
 *
 * @param props - Settings and the save callback.
 * @returns The section body.
 */
export function PermissionsSection({ settings, onSaved }: PermissionsSectionProps) {
  const [saving, setSaving] = useState(false);

  const change = async (tool: string, policy: string) => {
    setSaving(true);
    try {
      const updated = await patchSettings({
        tool_permissions: { ...settings.tool_permissions, [tool]: policy },
      });
      onSaved(updated);
      toast.success("Permission saved.");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-2">
      {TOOL_ROWS.map((row) => (
        <div
          key={row.tool}
          className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"
        >
          <div className="min-w-0">
            <p className="text-xs font-medium">
              <code className="font-mono text-[11px]">{row.tool}</code>{" "}
              <span className="text-muted-foreground">{row.label}</span>
            </p>
            <p className="text-[10px] text-muted-foreground">{row.description}</p>
          </div>
          <Select
            items={POLICY_OPTIONS}
            value={settings.tool_permissions[row.tool] ?? "ask"}
            onValueChange={(value) => void change(row.tool, String(value))}
          >
            <SelectTrigger
              aria-label={`${row.tool} approval`}
              className="w-24"
              disabled={saving}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {POLICY_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ))}
    </div>
  );
}
