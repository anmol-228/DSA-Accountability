/*
 * page-bridge.js — runs in the LeetCode PAGE context (not the isolated
 * content-script context), because Monaco's editor instances are only
 * reachable from page context. It never touches cookies, auth tokens, or
 * anything except the code editor's current text.
 *
 * Communicates with content-script.js via window.postMessage with a
 * namespaced message type, since page context and content-script context
 * cannot share JS objects directly.
 */
(function () {
  const REQUEST_TYPE = "DSA_ACCOUNTABILITY_REQUEST_CODE";
  const RESPONSE_TYPE = "DSA_ACCOUNTABILITY_CODE_RESULT";

  function tryMonacoGlobal() {
    try {
      if (window.monaco && window.monaco.editor) {
        const models = window.monaco.editor.getModels();
        if (models && models.length > 0) {
          // Prefer the model whose language is java if multiple are open.
          const javaModel = models.find((m) => m.getLanguageId && m.getLanguageId() === "java");
          const model = javaModel || models[0];
          return { code: model.getValue(), language: javaModel ? "java" : null, method: "monaco_global" };
        }
      }
    } catch (e) {
      /* fall through to next strategy */
    }
    return null;
  }

  function tryReactFiberEditorInstance() {
    try {
      const editorRoot = document.querySelector(".monaco-editor");
      if (!editorRoot) return null;
      // Walk up to find an element carrying a React fiber / props key that
      // exposes the editor instance. This mirrors common userscript
      // techniques; brittle by nature, hence it's a fallback, not primary.
      let el = editorRoot;
      for (let i = 0; i < 6 && el; i++, el = el.parentElement) {
        const key = Object.keys(el).find(
          (k) => k.startsWith("__reactProps$") || k.startsWith("__reactInternalInstance$")
        );
        if (key) {
          const props = el[key];
          const editorInstance =
            props && (props.editor || (props.memoizedProps && props.memoizedProps.editor));
          if (editorInstance && typeof editorInstance.getValue === "function") {
            return { code: editorInstance.getValue(), language: null, method: "react_fiber" };
          }
        }
      }
    } catch (e) {
      /* fall through */
    }
    return null;
  }

  function tryDomTextReconstruction() {
    try {
      const viewLines = document.querySelector(".monaco-editor .view-lines");
      if (!viewLines) return null;
      const lineEls = Array.from(viewLines.querySelectorAll(".view-line"));
      if (lineEls.length === 0) return null;
      // .view-line elements are absolutely positioned; sort by their `top`
      // offset so the reconstructed text is in the right order.
      lineEls.sort((a, b) => {
        const topA = parseFloat(a.style.top || "0");
        const topB = parseFloat(b.style.top || "0");
        return topA - topB;
      });
      const text = lineEls.map((el) => el.innerText.replace(/ /g, " ")).join("\n");
      return { code: text, language: null, method: "dom_reconstruction" };
    } catch (e) {
      return null;
    }
  }

  function captureCode() {
    return tryMonacoGlobal() || tryReactFiberEditorInstance() || tryDomTextReconstruction() || null;
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (!event.data || event.data.type !== REQUEST_TYPE) return;
    const result = captureCode();
    window.postMessage(
      {
        type: RESPONSE_TYPE,
        requestId: event.data.requestId,
        result,
      },
      "*"
    );
  });

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      tryMonacoGlobal, tryReactFiberEditorInstance, tryDomTextReconstruction, captureCode,
    };
  }
})();
