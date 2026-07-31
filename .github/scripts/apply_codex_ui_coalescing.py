from pathlib import Path
from textwrap import dedent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one {label} match, found {count}")
    return text.replace(old, new, 1)


def patch_renderer(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''    let assistantRenderFrame = 0;
    let streamActive = false;
    let streamFollowing = false;
''',
        '''    let assistantRenderFrame = 0;
    let pendingToolStick = false;
    let streamActive = false;
    let streamFollowing = false;
    const toolRenderQueue = createFrameCoalescer({
      requestFrame: (callback) => window.requestAnimationFrame(callback),
      cancelFrame: (frame) => window.cancelAnimationFrame(frame),
      onFlush(items) {
        const shouldStick = pendingToolStick;
        pendingToolStick = false;
        items.forEach(renderToolCall);
        keepBottomIfNeeded(shouldStick);
      },
    });
''',
        "renderer state",
    )
    text = replace_once(
        text,
        '''      streamActive = false;
      streamFollowing = false;
      clearPendingAssistantRender();
''',
        '''      streamActive = false;
      streamFollowing = false;
      clearPendingToolRenders();
      clearPendingAssistantRender();
''',
        "clear pending render",
    )
    text = replace_once(
        text,
        '''    function beginStream() {
      flushAssistantRender();
''',
        '''    function beginStream() {
      flushToolRenders();
      flushAssistantRender();
''',
        "begin stream",
    )
    text = replace_once(
        text,
        '''    function endStream() {
      flushAssistantRender();
''',
        '''    function endStream() {
      flushToolRenders();
      flushAssistantRender();
''',
        "end stream",
    )
    text = replace_once(
        text,
        '''    function resetStreamState() {
      flushAssistantRender();
''',
        '''    function resetStreamState() {
      flushToolRenders();
      flushAssistantRender();
''',
        "reset stream",
    )
    text = replace_once(
        text,
        '''    function resetActiveAssistant() {
      flushAssistantRender();
''',
        '''    function resetActiveAssistant() {
      flushToolRenders();
      flushAssistantRender();
''',
        "reset assistant",
    )
    text = replace_once(
        text,
        '''    function startThinkingCard() {
      const card = document.createElement("details");
''',
        '''    function startThinkingCard() {
      flushToolRenders();
      const card = document.createElement("details");
''',
        "thinking card",
    )
    text = replace_once(
        text,
        '''    function updateAssistantText(text) {
      if (!activeAssistant && !String(text || "").trim()) {
''',
        '''    function updateAssistantText(text) {
      flushToolRenders();
      if (!activeAssistant && !String(text || "").trim()) {
''',
        "assistant update",
    )

    start = text.index("    function updateToolCall(item) {\n")
    end = text.index("\n    function isTerminalToolStatus(status) {", start)
    replacement = dedent(
        '''\
            function updateToolCall(item) {
              clearGenerationStatus();
              const update = item || {};
              const id = update.id || "tool_call";
              pendingToolStick = pendingToolStick || isNearBottom();
              toolRenderQueue.schedule(id, update);
            }

            function flushToolRenders() {
              toolRenderQueue.flush();
            }

            function clearPendingToolRenders() {
              toolRenderQueue.clear();
              pendingToolStick = false;
            }

            function renderToolCall(item) {
              const id = item.id || "tool_call";
              let node = activeTools.get(id);
              if (!node || !node.isConnected) {
                flushAssistantRender();
                node = document.createElement("details");
                node.className = "tool-call";
                node.open = !isTerminalToolStatus(item.status || "in_progress");
                node.innerHTML = [
                  "<summary>",
                  '<span class="tool-chevron" aria-hidden="true">›</span>',
                  '<span class="tool-status" aria-hidden="true"></span>',
                  "<code></code>",
                  "<span></span>",
                  "</summary>",
                  '<div class="tool-body markdown-body"></div>',
                ].join("");
                insertToolNode(node);
                activeTools.set(id, node);
              }

              const status = item.status || "in_progress";
              node.classList.toggle("done", status === "done" || status === "completed");
              node.classList.toggle("failed", status === "failed");
              node.classList.toggle("timed-out", status === "timed_out");
              node.classList.toggle("cancelled", status === "cancelled");
              node.classList.toggle("denied", status === "denied");
              node.classList.toggle("pending-approval", status === "pending_approval");
              node.querySelector("code").textContent = item.name || "tool";
              node.querySelector("summary > span:last-child").textContent =
                toolStatusLabel(status);
              if (isTerminalToolStatus(status)) {
                node.open = false;
              } else if (status === "pending_approval") {
                node.open = true;
              }

              const body = node.querySelector(".tool-body");
              if (body) {
                chainToolBodyWheel(body);
                const content = item.content || approvalMarkdown(item.approval) || (item.arguments ? "```json\\n" + item.arguments + "\\n```" : "");
                const images = normalizeAttachments(item.images || item.attachments || []);
                renderMarkdown(body, content);
                const markdownImages = extractMarkdownImageAttachments(body);
                const toolImages = images.concat(markdownImages);
                if (toolImages.length > 0) {
                  body.append(renderAttachmentGrid(toolImages, "message-attachments tool-attachments"));
                }
                renderToolApproval(body, item.approval);
              }
            }
        '''
    )
    text = text[:start] + replacement + text[end:]

    text = replace_once(
        text,
        '''  function normalizeMarkdown(text) {
''',
        '''  function createFrameCoalescer(options) {
    const pending = new Map();
    let frame = 0;

    function drain() {
      if (!pending.size) {
        return;
      }
      const values = Array.from(pending.values());
      pending.clear();
      options.onFlush(values);
    }

    function schedule(key, value) {
      pending.set(String(key), value);
      if (frame) {
        return;
      }
      frame = options.requestFrame(() => {
        frame = 0;
        drain();
      });
    }

    function flush() {
      if (frame) {
        options.cancelFrame(frame);
        frame = 0;
      }
      drain();
    }

    function clear() {
      if (frame) {
        options.cancelFrame(frame);
        frame = 0;
      }
      pending.clear();
    }

    return {
      schedule,
      flush,
      clear,
      pendingCount: () => pending.size,
    };
  }

  function normalizeMarkdown(text) {
''',
        "frame coalescer",
    )
    text = replace_once(
        text,
        '''  window.FennaraTranscriptRenderer = { createTranscriptRenderer };
''',
        '''  window.FennaraTranscriptRenderer = {
    createTranscriptRenderer,
    _createFrameCoalescer: createFrameCoalescer,
  };
''',
        "renderer export",
    )
    path.write_text(text, encoding="utf-8")


source = Path("ui/chat/transcript-renderer.js")
dist = Path("godot_demo/addons/fennara/dist/transcript-renderer.js")
patch_renderer(source)
patch_renderer(dist)
if source.read_bytes() != dist.read_bytes():
    raise SystemExit("source and packaged transcript renderers diverged")


test_path = Path("ui/chat/tests/transcript-renderer-coalescing.test.js")
test_path.parent.mkdir(parents=True, exist_ok=True)
test_path.write_text(
    dedent(
        '''\
        "use strict";

        const assert = require("node:assert/strict");
        const fs = require("node:fs");
        const path = require("node:path");
        const vm = require("node:vm");

        global.window = {};
        const rendererPath = path.join(__dirname, "..", "transcript-renderer.js");
        vm.runInThisContext(fs.readFileSync(rendererPath, "utf8"), {
          filename: rendererPath,
        });

        const createFrameCoalescer =
          global.window.FennaraTranscriptRenderer._createFrameCoalescer;
        assert.equal(typeof createFrameCoalescer, "function");

        function createHarness() {
          let nextFrame = 1;
          const callbacks = new Map();
          const batches = [];
          const queue = createFrameCoalescer({
            requestFrame(callback) {
              const id = nextFrame++;
              callbacks.set(id, callback);
              return id;
            },
            cancelFrame(id) {
              callbacks.delete(id);
            },
            onFlush(items) {
              batches.push(items);
            },
          });
          return {
            queue,
            batches,
            callbacks,
            runFrame() {
              const entry = callbacks.entries().next().value;
              assert.ok(entry, "expected a scheduled animation frame");
              callbacks.delete(entry[0]);
              entry[1]();
            },
          };
        }

        {
          const harness = createHarness();
          for (let index = 0; index < 10_000; index += 1) {
            harness.queue.schedule("tool-1", { id: "tool-1", sequence: index });
          }
          assert.equal(harness.callbacks.size, 1);
          assert.equal(harness.queue.pendingCount(), 1);
          harness.runFrame();
          assert.equal(harness.batches.length, 1);
          assert.equal(harness.batches[0].length, 1);
          assert.equal(harness.batches[0][0].sequence, 9_999);
          assert.equal(harness.queue.pendingCount(), 0);
        }

        {
          const harness = createHarness();
          harness.queue.schedule("tool-a", { id: "tool-a", sequence: 1 });
          harness.queue.schedule("tool-b", { id: "tool-b", sequence: 2 });
          harness.queue.schedule("tool-a", { id: "tool-a", sequence: 3 });
          assert.equal(harness.callbacks.size, 1);
          harness.runFrame();
          assert.deepEqual(
            harness.batches[0].map((item) => [item.id, item.sequence]),
            [["tool-a", 3], ["tool-b", 2]],
          );
        }

        {
          const harness = createHarness();
          harness.queue.schedule("tool-final", { id: "tool-final", status: "done" });
          harness.queue.flush();
          assert.equal(harness.callbacks.size, 0);
          assert.equal(harness.batches.length, 1);
          assert.equal(harness.batches[0][0].status, "done");
          harness.queue.schedule("discarded", { id: "discarded" });
          harness.queue.clear();
          assert.equal(harness.callbacks.size, 0);
          assert.equal(harness.queue.pendingCount(), 0);
          assert.equal(harness.batches.length, 1);
        }

        console.log("transcript renderer tool updates coalesce per animation frame");
        '''
    ),
    encoding="utf-8",
)


doc = Path("docs/codex-app-server-ownership.md")
doc_text = doc.read_text(encoding="utf-8")
doc_text = replace_once(
    doc_text,
    '''| Event throughput | `burst_events_are_drained_without_blocking_the_runtime` and `external_tool_event_burst_does_not_block_the_app_server_stream` drain 10,000 synthetic events; the latter also includes MCP lifecycle events and enforces a 10-second CI budget. |
''',
    '''| Event throughput | `burst_events_are_drained_without_blocking_the_runtime` and `external_tool_event_burst_does_not_block_the_app_server_stream` drain 10,000 synthetic events; the latter also includes MCP lifecycle events and enforces a 10-second CI budget. |
| Embedded UI scheduling | `transcript-renderer-coalescing.test.js` submits 10,000 updates for one tool before an animation frame and verifies that only the newest state is rendered once. It also verifies independent tool IDs, synchronous terminal flush and cancellation cleanup. |
''',
    "performance matrix",
)
doc_text = replace_once(
    doc_text,
    '''The 10,000-event tests are regression guards for daemon/app-server backpressure and event-card processing. They demonstrate that using a tool does not synchronously block the provider stream under the synthetic workload. They are not a Godot frame-time benchmark. Real editor lag still depends on the selected Godot tool, project size, filesystem activity, imports and scene refresh work, so release testing should additionally profile Godot frame time and editor responsiveness on representative projects.
''',
    '''The daemon-side 10,000-event tests are regression guards for app-server backpressure and event-card processing. The embedded transcript renderer additionally coalesces repeated updates for the same tool ID and renders only the newest state once per animation frame; stream completion, cancellation and reset synchronously flush or discard pending state. This removes event-rate-proportional Markdown parsing, DOM replacement and layout work from the Godot WebView path.

These automated checks demonstrate that tool progress traffic does not synchronously block the provider stream or force one UI render per event. They are not a full Godot frame-time benchmark. Real editor lag can still be caused by the selected Godot tool, project size, filesystem activity, asset imports and scene refresh work, so release testing should additionally profile Godot frame time and editor responsiveness on representative projects.
''',
    "performance interpretation",
)
doc.write_text(doc_text, encoding="utf-8")
