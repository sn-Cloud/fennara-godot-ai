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
