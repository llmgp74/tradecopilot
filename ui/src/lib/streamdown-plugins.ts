import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import { createMathPlugin } from "@streamdown/math";
import { mermaid } from "@streamdown/mermaid";

/**
 * Streamdown plugins shared by message and reasoning rendering.
 *
 * Single-dollar inline math is enabled so `$x$` renders. A paragraph holding
 * two separate dollar signs is read as one formula, so the system prompt keeps
 * money out of prose that already contains a dollar sign.
 */
export const streamdownPlugins = {
  cjk,
  code,
  math: createMathPlugin({ singleDollarTextMath: true }),
  mermaid,
};
