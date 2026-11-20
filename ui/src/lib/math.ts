import type { Root, RootContent } from "mdast";

/** Marker pairs that survive markdown parsing for inline and display math. */
const MARKS = {
  inline: { open: "\uE000", close: "\uE001" },
  display: { open: "\uE002", close: "\uE003" },
} as const;

const INLINE = /\\\(([^\n]+?)\\\)/g;
const DISPLAY = /\\\[([\s\S]+?)\\\]/g;

/**
 * Replaces `\( ... \)` and `\[ ... \]` math with private-use markers.
 *
 * The markers survive markdown parsing, where a backslash escapes the
 * bracket and the math would otherwise become plain text. Single dollar
 * signs are not used because they collide with currency amounts.
 *
 * @param text - Raw assistant markdown.
 * @returns The markdown with math marked.
 */
export function markInlineMath(text: string): string {
  return text
    .replace(
      INLINE,
      (_match, formula: string) =>
        `${MARKS.inline.open}${formula.trim()}${MARKS.inline.close}`,
    )
    .replace(
      DISPLAY,
      (_match, formula: string) =>
        `${MARKS.display.open}${formula.trim()}${MARKS.display.close}`,
    );
}

/**
 * Builds the mdast node remark-math uses for one formula.
 *
 * @param formula - TeX source.
 * @param display - True for a block equation.
 * @returns The node, shaped so the KaTeX rehype plugin renders it.
 */
function mathNode(formula: string, display: boolean): RootContent {
  return {
    type: display ? "math" : "inlineMath",
    value: formula,
    data: {
      hName: "code",
      hProperties: {
        className: ["language-math", display ? "math-display" : "math-inline"],
      },
      hChildren: [{ type: "text", value: formula }],
    },
  } as unknown as RootContent;
}

/**
 * Splits one text value into text and math nodes for one marker pair.
 *
 * @param value - Text containing marked math.
 * @param marks - Marker pair to split on.
 * @param display - True for a block equation.
 * @returns Replacement nodes in order.
 */
function split(
  value: string,
  marks: { open: string; close: string },
  display: boolean,
): RootContent[] {
  const nodes: RootContent[] = [];
  let last = 0;
  const pattern = new RegExp(`${marks.open}([\\s\\S]*?)${marks.close}`, "g");
  for (const match of value.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > last) {
      nodes.push({ type: "text", value: value.slice(last, index) } as RootContent);
    }
    nodes.push(mathNode(match[1], display));
    last = index + match[0].length;
  }
  if (nodes.length === 0) {
    return [{ type: "text", value } as RootContent];
  }
  if (last < value.length) {
    nodes.push({ type: "text", value: value.slice(last) } as RootContent);
  }
  return nodes;
}

/**
 * Applies both marker pairs to one text value.
 *
 * @param value - Text containing marked math.
 * @returns Replacement nodes in order.
 */
function splitAll(value: string): RootContent[] {
  return split(value, MARKS.inline, false).flatMap((node) =>
    node.type === "text"
      ? split((node as { value: string }).value, MARKS.display, true)
      : [node],
  );
}

type Walkable = { type: string; value?: unknown; children?: unknown[] };

/**
 * Rewrites marked text into math nodes, skipping code.
 *
 * @param node - Tree node to walk.
 */
function walk(node: Walkable): void {
  if (!Array.isArray(node.children)) {
    return;
  }
  const next: unknown[] = [];
  for (const child of node.children) {
    const item = child as Walkable;
    if (
      item.type === "text" &&
      typeof item.value === "string" &&
      (item.value.includes(MARKS.inline.open) || item.value.includes(MARKS.display.open))
    ) {
      next.push(...splitAll(item.value));
      continue;
    }
    if (item.type !== "code" && item.type !== "inlineCode") {
      walk(item);
    }
    next.push(item);
  }
  node.children = next;
}

/**
 * Remark plugin that turns marked math into KaTeX-rendered nodes.
 *
 * @returns The transformer.
 */
export function remarkInlineMath() {
  return (tree: Root): void => {
    walk(tree as unknown as Walkable);
  };
}
