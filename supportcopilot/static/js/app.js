// SupportCopilot — small client helpers (theme toggle, chat UX, examples).
(function () {
  "use strict";

  // ---- Theme (light/dark) with persistence + system fallback -------------
  const root = document.documentElement;
  const THEME_KEY = "supportcopilot-theme";

  function applyTheme(theme) {
    if (theme === "dark") root.classList.add("dark");
    else root.classList.remove("dark");
  }

  function initTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved) {
      applyTheme(saved);
    } else {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      applyTheme(prefersDark ? "dark" : "light");
    }
  }

  window.toggleTheme = function () {
    const isDark = root.classList.toggle("dark");
    localStorage.setItem(THEME_KEY, isDark ? "dark" : "light");
  };

  // ---- Chat helpers -------------------------------------------------------
  function scrollThread() {
    const thread = document.getElementById("thread");
    if (thread) thread.scrollTop = thread.scrollHeight;
  }
  window.scrollThread = scrollThread;

  // Clicking an example chip fills the form and submits it.
  window.useExample = function (message, orderId, email) {
    const msg = document.getElementById("message");
    const oid = document.getElementById("order_id");
    const mail = document.getElementById("email");
    if (msg) msg.value = message || "";
    if (oid) oid.value = orderId || "";
    if (mail) mail.value = email || "";
    const form = document.getElementById("chat-form");
    if (form && window.htmx) {
      window.htmx.trigger(form, "submit");
    }
    if (msg) msg.focus();
  };

  // Keep the thread pinned to the newest message after each htmx swap.
  document.addEventListener("htmx:afterSwap", function (e) {
    if (e.target && e.target.id === "thread") scrollThread();
  });

  // Initialize theme as early as possible to avoid a flash.
  initTheme();
  document.addEventListener("DOMContentLoaded", scrollThread);
})();
