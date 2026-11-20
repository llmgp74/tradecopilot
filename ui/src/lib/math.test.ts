import { expect, it } from "vitest";
import remarkParse from "remark-parse";
import remarkRehype from "remark-rehype";
import { unified } from "unified";
import { defaultRemarkPlugins } from "streamdown";
import { markInlineMath, remarkInlineMath, remarkPlugins } from "./math";

/** One hast node shape, narrowed to what the assertions read. */
interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: { className?: string[] };
  children?: HastNode[];
}

it("renders parenthesized math as an inline math node", async () => {
  const processor = unified().use(remarkParse).use(remarkInlineMath).use(remarkRehype);
  const mdast = processor.parse(markInlineMath("The drag is \\(F = ma\\) today."));
  const hast = (await processor.run(mdast)) as unknown as { children: HastNode[] };

  const paragraph = hast.children[0];
  const math = paragraph.children?.find((node) => node.tagName === "code");

  expect(math?.properties?.className).toEqual(["language-math", "math-inline"]);
  expect(math?.children?.[0]?.value).toBe("F = ma");
});

it("renders bracket math as a display equation", async () => {
  const processor = unified().use(remarkParse).use(remarkInlineMath).use(remarkRehype);
  const mdast = processor.parse(markInlineMath("\\[\nA = P(1 + r)^t\n\\]"));
  const hast = (await processor.run(mdast)) as unknown as { children: HastNode[] };

  const paragraph = hast.children[0];
  const code = paragraph.children?.find((node) => node.tagName === "code");

  expect(code?.properties?.className).toEqual(["language-math", "math-display"]);
});

it("keeps the Streamdown defaults so GFM tables still parse", () => {
  expect(remarkPlugins).toEqual([
    ...Object.values(defaultRemarkPlugins),
    remarkInlineMath,
  ]);
});

it("parses GFM tables with the plugin list", () => {
  const processor = unified().use(remarkParse).use(remarkPlugins).use(remarkRehype);
  const mdast = processor.parse("| Ticker | Cost |\n|---|---|\n| SGOV | $96,020 |");

  expect(mdast.children[0].type).toBe("table");
});

it("leaves currency amounts untouched", () => {
  const text = "The order is $98,960 of the $990,322 account.";

  expect(markInlineMath(text)).toBe(text);
});
