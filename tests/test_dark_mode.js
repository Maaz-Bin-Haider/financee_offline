/* Real theme scripts in a small DOM: no browser/package dependency. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'static/js/dark_mode.js'), 'utf8');
let checks = 0;
function check(name, fn) { fn(); checks++; console.log('PASS:', name); }
function node() {
  const classes = new Set();
  return {classList: {
    add: name => classes.add(name), remove: name => classes.delete(name),
    contains: name => classes.has(name),
    toggle(name, on) { if (on) classes.add(name); else classes.delete(name); }
  }, attrs: {}, events: {}, textContent: '',
  setAttribute(name, value) { this.attrs[name] = value; },
  addEventListener(name, fn) { this.events[name] = fn; }};
}
function environment(value, blocked = false, withButton = true) {
  const elements = Object.fromEntries(['themeToggle', 'themeIcon', 'themeText'].map(id => [id, node()]));
  const document = {documentElement: node(), body: node(),
    getElementById: id => withButton ? elements[id] : null};
  const events = {};
  const storage = {value, getItem() { if (blocked) throw Error('blocked'); return this.value; },
    setItem(key, v) { if (blocked) throw Error('blocked'); this.value = v; }};
  const context = {document, localStorage: storage,
    window: {addEventListener: (name, fn) => { events[name] = fn; }},
    setTimeout: () => 1, clearTimeout() {}};
  return {context, document, elements, storage, events,
    dark: () => document.documentElement.classList.contains('dark-mode')};
}
for (const value of [null, 'dark', 'auto']) {
  check(`dark default for ${value}`, () => {
    const e = environment(value); vm.runInNewContext(source, e.context);
    assert(e.dark()); assert(e.document.body.classList.contains('dark-mode'));
    assert.equal(e.elements.themeToggle.attrs['aria-pressed'], 'true');
    assert.equal(e.elements.themeText.textContent, 'Light Mode');
  });
}
check('saved light preference survives load', () => {
  const e = environment('light'); vm.runInNewContext(source, e.context); assert(!e.dark());
});
check('toggle persists both directions and updates the label', () => {
  const e = environment(null); vm.runInNewContext(source, e.context);
  e.elements.themeToggle.events.click(); assert(!e.dark()); assert.equal(e.storage.value, 'light');
  assert.equal(e.elements.themeText.textContent, 'Dark Mode');
  e.elements.themeToggle.events.click(); assert(e.dark()); assert.equal(e.storage.value, 'dark');
});
check('blocked storage stays usable and defaults dark', () => {
  const e = environment(null, true); vm.runInNewContext(source, e.context);
  assert(e.dark()); e.elements.themeToggle.events.click(); assert(!e.dark());
});
check('missing toggle does not break standalone pages', () => {
  const e = environment(null, false, false); vm.runInNewContext(source, e.context); assert(e.dark());
});
check('cross-tab updates and cleared preferences agree with first visit', () => {
  const e = environment(null); vm.runInNewContext(source, e.context);
  e.events.storage({key: 'theme', newValue: 'light'}); assert(!e.dark());
  e.events.storage({key: 'theme', newValue: null}); assert(e.dark());
  e.events.storage({key: 'unrelated', newValue: 'light'}); assert(e.dark());
  e.events.storage({key: null, newValue: null}); assert(e.dark());
});
for (const template of ['base/base.html', 'authentication_templates/login_template.html',
                        'tenancy_templates/subscription_suspended.html']) {
  check(`${template} applies the same preference before stylesheets`, () => {
    const html = fs.readFileSync(path.join(root, 'templates', template), 'utf8');
    const script = html.match(/<script>([\s\S]*?)<\/script>/);
    assert(script); assert(html.indexOf(script[0]) < html.indexOf('<link'));
    for (const [value, blocked, dark] of [[null, false, true], ['light', false, false],
                                         ['dark', false, true], [null, true, true]]) {
      const e = environment(value, blocked); vm.runInNewContext(script[1], e.context);
      assert.equal(e.dark(), dark);
    }
  });
}
console.log(`${checks} theme behavior checks passed.`);
