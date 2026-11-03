# AGENTS.md

Rules for all code, comments, and documentation in this repository.

This is a uv workspace: Python in `agent/` and `eval/`, React/TypeScript in
`ui/`.

## 1. Use ASCII for English text

Write code, comments, and documentation in English using ASCII characters.
Use a non-ASCII character only when it carries meaning, such as an accented
name or a symbol with no ASCII form. Do not use em dashes, curly quotes,
emojis, or other typographic characters in English text.

Do not imitate a non-ASCII character with broken ASCII. If a sentence needs
a dash, use a plain hyphen that reads correctly, or rewrite the sentence. In
prose, do not write `--` for an em dash, `->` for an arrow, or `(c)` for the
copyright sign.

The rule applies to English only. Text in another language, such as Chinese,
may use its native UTF-8 characters.

## 2. Lint every file you touch

Run the linters for the language of every file you create or edit, and fix
all errors before finishing.

| Language | Tool | Command |
| --- | --- | --- |
| Markdown | markdownlint | `markdownlint <file>` |
| Python | Ruff (lint) | `uv run ruff check <path>` |
| Python | Ruff (format) | `uv run ruff format --check <path>` |
| Python | mypy | `uv run mypy <path>` |
| TypeScript/JS | ESLint | `npm run lint` |
| TypeScript | tsc | `npx tsc --noEmit` |
| TypeScript/JS | Prettier | `npx prettier --check <file>` |
| YAML | yamllint | `yamllint <file>` |
| Shell | shellcheck | `shellcheck <file>` |
| Dockerfile | hadolint | `hadolint Dockerfile` |

Run Python commands from the package directory (`agent/` or `eval/`) and
JS/TS commands from `ui/`. Skip a tool only when the language is not present
in the change; do not skip it because it reports many errors.

A rule may be disabled only for a concrete reason in the lint configuration,
never silently.

Also run the tests for every touched package before finishing:
`uv run pytest` from `agent/` or `eval/`, `npm test` from `ui/`.

## 3. Write clean code and clear comments

Use the language's standard documentation form:

- Python: docstrings (PEP 257, Google style) on every public module, class,
  and function: parameters, return values, raised errors, constraints. Type
  hints on every signature.
- TypeScript/JavaScript: TSDoc/JSDoc on exported functions, types, and
  components: props, return values, side effects.

Document private items when their purpose is not obvious.

Comment logic only where the code cannot explain itself: why it exists, the
invariants it relies on, and the traps it avoids. Do not narrate what the code
already says. Never write chain-of-thought, reasoning steps, plans, or
unrelated notes in comments.

Use `TODO:` for deferred work and `FIXME:` for known defects, in the
language's comment syntax (`# TODO:` in Python, `// TODO:` in TS). State the
concrete action or reason, and remove the marker when the work is done.

Keep these rules from Clean Code by Robert C. Martin:

- Names say what they mean. Avoid abbreviations and misleading names.
- Functions are small, do one thing, and stay at one level of abstraction.
- No dead code, commented-out code, or speculative abstraction.
- Handle errors explicitly; never swallow them.
- Match the formatting and structure of the surrounding code.
