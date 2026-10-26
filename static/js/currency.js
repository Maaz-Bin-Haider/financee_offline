/* Installation currency labels. Financial values and two-decimal presentation
 * retain the existing contract; ISO minor units never change stored precision. */
(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory;
  if (root && root.document) {
    var node = root.document.getElementById("financee-currency");
    var config = node ? JSON.parse(node.textContent) : {};
    root.FinanceeMoney = factory(config);
    root.FINANCEE_CURRENCY = root.FinanceeMoney.code;
  }
}(typeof window !== "undefined" ? window : null, function (config) {
  "use strict";
  var code = String(config.code || "");
  var label = String(config.label || code);
  var number = new Intl.NumberFormat("en-AE", {minimumFractionDigits:2, maximumFractionDigits:2});
  function amount(value) { return parseFloat(value) || 0; }
  function format(value) { return (label ? label + " " : "") + number.format(amount(value)); }
  function axis(value) {
    var n = amount(value);
    return (label ? label + " " : "") + (n >= 1000 ? (n / 1000).toFixed(0) + "k" : String(n));
  }
  return Object.freeze({code:code, symbol:String(config.symbol || ""), label:label, format:format, axis:axis});
}));
