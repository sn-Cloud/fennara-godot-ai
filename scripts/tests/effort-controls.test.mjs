import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

class Element {
  hidden = true;
  children = [];
  listeners = {};
  attributes = {};
  addEventListener(name, fn) { this.listeners[name] = fn; }
  setAttribute(name, value) { this.attributes[name] = value; }
  replaceChildren(...children) { this.children = children; }
  click() { this.listeners.click?.({ stopPropagation() {} }); }
}

test("official effort metadata drives menu, selection, fallback and unavailable state", () => {
  const context = { window: {}, document: { createElement: () => new Element() } };
  vm.runInNewContext(readFileSync(new URL("../../ui/chat/effort-controls.js", import.meta.url), "utf8"), context);
  const effortToggle = new Element(), effortOptions = new Element(), effortStatus = new Element();
  let current = "medium", saved;
  const controls = context.window.FennaraEffortControls.createEffortControls({
    elements: { effortToggle, effortOptions, effortStatus },
    callbacks: {
      getCurrentReasoningEffort: () => current,
      setCurrentReasoningEffort: (value) => { current = value; },
      saveCurrentChatSettings: () => { saved = current; },
    },
  });
  controls.updateForModel({ supported_reasoning_efforts: ["low", "ultra", "future_effort"], default_reasoning_effort: "ultra" });
  assert.equal(current, "ultra");
  assert.deepEqual(effortOptions.children.map((button) => button.value), ["low", "ultra", "future_effort"]);
  effortToggle.click();
  assert.equal(effortOptions.hidden, false);
  effortOptions.children[2].click();
  assert.equal(saved, "future_effort");
  assert.equal(effortStatus.textContent, "Future_effort");
  assert.equal(effortOptions.hidden, true);
  controls.updateForModel({ supported_reasoning_efforts: ["low", "high"], default_reasoning_effort: "high" });
  assert.equal(current, "high");
  controls.updateForModel(null);
  assert.equal(effortToggle.disabled, true);
  assert.equal(effortOptions.children.length, 0);
});
