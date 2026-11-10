/**
 * Builds a Server-Sent Events response from UI message stream parts.
 *
 * @param frames - Stream chunks, one per frame.
 * @returns A streamed `Response` the AI SDK transport can parse.
 */
export function sseResponse(frames: object[]): Response {
  const text =
    frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join("") +
    "data: [DONE]\n\n";
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(text));
        controller.close();
      },
    }),
    {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "x-vercel-ai-ui-message-stream": "v1",
      },
    },
  );
}
