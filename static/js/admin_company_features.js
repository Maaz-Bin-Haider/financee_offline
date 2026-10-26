/*
 * Company admin: nest each feature's sub-switches under its main switch.
 *
 * tenancy/admin.py marks every feature checkbox: data-feature-master (a main
 * switch with sub-features), data-feature-single (a switch without any) or
 * data-feature-parent (a sub-feature). Sub-feature rows are indented, and
 * dimmed while their main switch is off. Their ticks are kept and still
 * submitted: switching the main switch back on restores them.
 */
(function () {
  "use strict";

  function rowOf(input) {
    return input.closest(".form-row") || input.parentElement;
  }

  function init() {
    document.querySelectorAll("input[data-feature-single]").forEach(function (input) {
      rowOf(input).classList.add("feature-master-row");
    });
    document.querySelectorAll("input[data-feature-parent]").forEach(function (input) {
      rowOf(input).classList.add("feature-sub-row");
    });
    document.querySelectorAll("input[data-feature-master]").forEach(function (master) {
      rowOf(master).classList.add("feature-master-row");
      var group = master.getAttribute("data-feature-master");
      var subs = document.querySelectorAll('input[data-feature-parent="' + group + '"]');
      var sync = function () {
        subs.forEach(function (sub) {
          rowOf(sub).classList.toggle("feature-sub-muted", !master.checked);
        });
      };
      master.addEventListener("change", sync);
      sync();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
