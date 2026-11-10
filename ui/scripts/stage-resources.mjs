import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const ui = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = resolve(ui, "..");
const out = join(ui, "src-tauri", "resources");

rmSync(join(out, "agent"), { recursive: true, force: true });
mkdirSync(out, { recursive: true });

execFileSync(
  "uv",
  [
    "export",
    "--frozen",
    "--package",
    "tradecopilot-agent",
    "--no-dev",
    "--no-emit-project",
    "--no-hashes",
    "-o",
    join(out, "requirements.lock.txt"),
  ],
  { cwd: root, stdio: "inherit" },
);

cpSync(join(root, "agent"), join(out, "agent"), {
  recursive: true,
  filter: (source) => {
    const parts = source.split(sep);
    const name = parts[parts.length - 1];
    // Hidden directories such as .mypy_cache are large and not needed.
    return (
      !name.startsWith(".") && !parts.includes("__pycache__") && !parts.includes("tests")
    );
  },
});
