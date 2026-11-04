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

## 4. Write plain prose

These rules apply to documentation, comments, commit messages, help text,
error messages, and chat or agent responses. They apply to text from any
author or tool. Generated text often falls into these patterns, but the
rules concern the result, not how the text was produced. Remove filler;
do not make the writing formal or stiff.

### Say something in every sentence

- Every sentence must add information the reader does not already have.
  Delete a sentence that restates the previous one, announces the next
  one, or claims that something is important.
- Name the actor and the action. Prefer `is`, `has`, `use`, `help`,
  `show`, `start`, `include`, and `many` over longer substitutes.
- Be specific. A number, path, command, version, or named source carries
  more meaning than an adjective. Write `the backup runs every 15
  minutes`, not `a robust backup strategy`.
- Put the conclusion first. Explain it after, not before.

### Avoid these sentence shapes

- Negative parallelism: `It's not X, it's Y`, `not just X but Y`,
  `That's not X, that's Y`.
- Fake suspense: `The result?`, `The answer?`, `And the best part?`,
  `Here's the thing`, `Here's what you need to know`.
- Fragment chains: `No setup. No config. Just work.` and
  `Fast. Simple. Reliable.`
- Closers that repeat the section: `That is the real win.` End on the
  last concrete fact.
- Inflated significance: `plays a key role`, `stands as a testament`,
  `marks a pivotal moment`, `leaves a lasting legacy`.
- Unnamed authority: `studies show`, `experts agree`, `research
  suggests`. Name the source, link it, or cut the claim.
- Staged openings: `Let's dive in`, `Let's explore`, `In today's
  fast-paced world`, `When it comes to`.
- Riders that interpret a fact instead of adding one: `..., highlighting
  the importance of...`, `..., underscoring how...`, `..., ensuring a
  seamless experience`.

### Avoid these words in prose

The problem is density, not a single occurrence. One use is not a defect,
and a technical term keeps its technical meaning. Replace the word when
the plain alternative says the same thing.

- `delve` (look at, dig into)
- `utilize`, `leverage` (use)
- `facilitate` (help)
- `elucidate` (explain)
- `embark` (start)
- `endeavor` (try)
- `encompass` (include)
- `showcase` (show)
- `underscore` as a verb (show, stress)
- `catalyze`, `galvanize` (trigger, spur)
- `spearhead` (lead)
- `supercharge` (boost)
- `revolutionize` (change)
- `tapestry`, `myriad`, `plethora` (mix, many, plenty)
- `testament` (shows)
- `multifaceted` (complex)
- `holistic` (whole)
- `synergy` (teamwork)
- `paradigm` (model)
- `realm` (area)
- `meticulous` (careful)
- `cutting-edge`, `groundbreaking`, `transformative`, `unprecedented`
  (new, first, big, rare)
- `bespoke` (custom)
- `unwavering` (steady)
- `game-changer` (major change)

Watch for clusters of promotional adjectives: `seamless`, `robust`,
`comprehensive`, `pivotal`, `innovative`, `streamline`, `empower`,
`foster`, `enhance`, `elevate`, `optimize`, `scalable`. Each can be
correct in a technical sentence. Four in one paragraph usually means the
paragraph has no specifics.

### Structure paragraphs and headings

- Start a paragraph with its subject. Do not open consecutive paragraphs
  with `However`, `Additionally`, `Moreover`, or `Furthermore`.
- Use sentence case in headings. Do not add decorations, emojis, or
  arrows.
- Do not bold words in body text for emphasis. Bold a label only when the
  label carries information the reader needs.
- A heading should not repeat the document title. Do not start a section
  with a sentence that repeats its heading.

### Check the text before finishing

Read the prose as someone who already knows the background. Cut every
sentence that only restates context. Search for the words and shapes
above, then replace the ones that add no meaning. Keep every supported
claim, and do not invent specifics to replace a vague phrase. Quoted text
may keep its original wording. Wrap an example in a code span so it reads
as an example.
