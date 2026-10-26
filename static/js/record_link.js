/* Strict record links, consumed once. The server resolves IDs in the current company. */
(function (root) {
  'use strict';
  function number(value) {
    const text = String(value == null ? '' : value);
    return /^[1-9][0-9]{0,15}$/.test(text) && Number.isSafeInteger(Number(text)) ? text : null;
  }
  function split(search, names) {
    const params = new URLSearchParams(search), values = {};
    let found = false;
    for (const name of names) {
      if (!params.has(name)) continue;
      found = true; values[name] = params.get(name); params.delete(name);
    }
    return { values, found, search: params.size ? '?' + params.toString() : '' };
  }
  function take(names) {
    const value = split(root.location.search, Array.isArray(names) ? names : [names]);
    if (value.found) root.history.replaceState(root.history.state, '', root.location.pathname + value.search + root.location.hash);
    return value.values;
  }
  function report(allowed, fallback) {
    const value = take('report').report;
    return allowed.includes(value) ? value : fallback;
  }
  const api = { number, split, take, report };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.FinanceeRecordLink = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
