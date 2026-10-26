/*
 * Dark mode toggle. The choice is per browser: localStorage 'theme' holds
 * 'dark' or 'light'.
 *
 * Dark is the default, matching Accounting: only an explicit 'light' turns
 * it off. Missing values, blocked storage and the admin's 'auto' value all
 * use dark. The <head> scripts in base.html, the
 * login page and the suspended page apply the class before first paint; this
 * file owns the sidebar toggle. Every place that decides the theme must
 * agree -- see PROJECT_CONTEXT.md, Dark Mode.
 */
(function () {
  "use strict";

  var KEY = "theme";
  // dark_mode.css cross-fades the main surfaces over 380ms while
  // <html> carries .theme-switching; keep it a frame longer.
  var SWITCH_MS = 420;
  var switchTimer = null;

  function storedTheme() {
    try {
      return localStorage.getItem(KEY);
    } catch (e) {
      return null;
    }
  }

  function storeTheme(value) {
    try {
      localStorage.setItem(KEY, value);
    } catch (e) {
      /* storage blocked: the choice lasts for this page only */
    }
  }

  function updateButton(isDark) {
    var button = document.getElementById("themeToggle");
    if (!button) return;
    var icon = document.getElementById("themeIcon");
    var text = document.getElementById("themeText");
    button.setAttribute("aria-pressed", isDark ? "true" : "false");
    if (icon) {
      icon.classList.toggle("fa-moon", !isDark);
      icon.classList.toggle("fa-sun", isDark);
    }
    if (text) text.textContent = isDark ? "Light Mode" : "Dark Mode";
  }

  function applyTheme(isDark) {
    document.documentElement.classList.toggle("dark-mode", isDark);
    document.body.classList.toggle("dark-mode", isDark);
    updateButton(isDark);
  }

  function crossFade() {
    var html = document.documentElement;
    html.classList.add("theme-switching");
    clearTimeout(switchTimer);
    switchTimer = setTimeout(function () {
      html.classList.remove("theme-switching");
    }, SWITCH_MS);
  }

  applyTheme(storedTheme() !== "light");

  var toggle = document.getElementById("themeToggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var isDark = !document.documentElement.classList.contains("dark-mode");
      crossFade();
      applyTheme(isDark);
      storeTheme(isDark ? "dark" : "light");
    });
  }

  // Another tab switched the theme: follow it here too.
  window.addEventListener("storage", function (event) {
    if (event.key === KEY || event.key === null) {
      applyTheme(event.newValue !== "light");
    }
  });
})();
