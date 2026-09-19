(function () {
  function createEffortControls(options = {}) {
    const elements = options.elements || {};
    const callbacks = options.callbacks || {};
    const reasoningEffortControls = Array.from(elements.reasoningEffortControls || []);
    const effortStatus = elements.effortStatus || null;
    const effortToggle = elements.effortToggle || null;
    const effortOptions = elements.effortOptions || null;
    let effortOptionButtons = [];
    const getCurrentReasoningEffort = callbacks.getCurrentReasoningEffort || (() => "medium");
    const setCurrentReasoningEffort = callbacks.setCurrentReasoningEffort || function () {};
    const cleanReasoningEffort = callbacks.cleanReasoningEffort || ((effort) => effort || "medium");
    const saveCurrentChatSettings = callbacks.saveCurrentChatSettings || function () {};

    reasoningEffortControls.forEach((control) => {
      control.addEventListener("change", () => {
        const effort = cleanReasoningEffort(control.value);
        setCurrentReasoningEffort(effort);
        syncReasoningControls(effort);
        updateComposerEffort();
        saveCurrentChatSettings();
      });
    });

    effortToggle?.addEventListener("click", (event) => {
      event.stopPropagation();
      setEffortMenuOpen(effortOptions?.hidden !== false);
    });

    function bindOption(button) {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        const effort = cleanReasoningEffort(button.value);
        setCurrentReasoningEffort(effort);
        syncReasoningControls(effort);
        updateComposerEffort();
        setEffortMenuOpen(false);
        saveCurrentChatSettings();
      });
    }

    // Rebuild from the selected model's catalog metadata, including future effort values.
    // Missing metadata disables the control until a successful catalog response arrives.
    function updateForModel(model) {
      const efforts = Array.from(new Set(model?.supported_reasoning_efforts || []));
      if (effortToggle) effortToggle.disabled = efforts.length === 0;
      setEffortMenuOpen(false);
      effortOptionButtons = efforts.map((effort) => {
        const button = document.createElement("button");
        button.type = "button";
        button.setAttribute("role", "option");
        button.setAttribute("data-effort-option", "");
        button.value = effort;
        button.textContent = effortLabel(effort);
        bindOption(button);
        return button;
      });
      effortOptions?.replaceChildren(...effortOptionButtons);
      if (efforts.length && !efforts.includes(getCurrentReasoningEffort())) {
        const preferred = model.default_reasoning_effort;
        setCurrentReasoningEffort(efforts.includes(preferred) ? preferred : efforts[0]);
      }
      syncReasoningControls();
      updateComposerEffort();
    }

    function syncReasoningControls(effort = getCurrentReasoningEffort()) {
      reasoningEffortControls.forEach((control) => {
        control.value = effort;
      });
    }

    function effortLabel(effort) {
      return effort.charAt(0).toUpperCase() + effort.slice(1);
    }

    function updateComposerEffort() {
      const effort = getCurrentReasoningEffort();
      if (effortStatus) {
        effortStatus.textContent = effortOptionButtons.length ? effortLabel(effort) : "Effort unavailable";
      }
      effortOptionButtons.forEach((button) => {
        const selected = button.value === effort;
        button.setAttribute("aria-selected", String(selected));
      });
    }

    function setEffortMenuOpen(open) {
      if (!effortOptions || !effortToggle) {
        return;
      }
      effortOptions.hidden = !open;
      effortToggle.setAttribute("aria-expanded", String(open));
    }

    return {
      setEffortMenuOpen,
      syncReasoningControls,
      updateComposerEffort,
      updateForModel,
    };
  }

  window.FennaraEffortControls = {
    createEffortControls,
  };
})();
