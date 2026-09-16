"""Resolve a click or fill target from a CSS selector or plain visible text.

An agent driving a page it cannot see has to name things the way a person
would — "Sign in", not "#login-form > button:nth-of-type(2)". One in-page pass
classifies the argument, and when it is text rather than a selector it returns
the matching elements, each with the simplest selector that uniquely identifies
it, so an ambiguous instruction comes back as a list to choose from instead of
a guess.

Lifted from p0o's `ui` layer, where it replaced selector-guessing.
"""
from plc import BrowserError, evaluate_json, js_string

HELPERS_JS = r"""
const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
const isVisible = (el) => {
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return false;
  const st = window.getComputedStyle(el);
  return st.visibility !== 'hidden' && st.display !== 'none';
};
const isEnabled = (el) => !el.disabled && el.getAttribute('aria-disabled') !== 'true';
const uniq = (sel) => { try { return document.querySelectorAll(sel).length === 1; } catch (e) { return false; } };
const cssPath = (el) => {
  const parts = [];
  let node = el;
  while (node && node.nodeType === 1 && node.tagName !== 'HTML') {
    if (node.id && uniq('#' + CSS.escape(node.id))) { parts.unshift('#' + CSS.escape(node.id)); break; }
    let part = node.tagName.toLowerCase();
    const parent = node.parentElement;
    if (parent) {
      const kin = Array.from(parent.children).filter((c) => c.tagName === node.tagName);
      if (kin.length > 1) part += ':nth-of-type(' + (kin.indexOf(node) + 1) + ')';
    }
    parts.unshift(part);
    node = node.parentElement;
  }
  return parts.join(' > ');
};
const bestSelector = (el) => {
  if (el.id && uniq('#' + CSS.escape(el.id))) return '#' + CSS.escape(el.id);
  const testid = el.getAttribute('data-testid');
  if (testid) { const s = '[data-testid=' + JSON.stringify(testid) + ']'; if (uniq(s)) return s; }
  if (el.classList.length) {
    const s = el.tagName.toLowerCase() + '.' + Array.from(el.classList).map((c) => CSS.escape(c)).join('.');
    if (uniq(s)) return s;
  }
  return cssPath(el);
};
const dropAncestors = (list) => list.filter((el) => !list.some((o) => o !== el && el.contains(o)));
"""

CLICK_JS = r"""
let selectorValid = true, selectorCount = 0, selectorVisibleCount = 0, selectorTarget = '';
try {
  const matches = Array.from(document.querySelectorAll(arg));
  selectorCount = matches.length;
  const actionable = matches.filter((el) => isVisible(el) && isEnabled(el));
  selectorVisibleCount = actionable.length;
  selectorTarget = actionable.length ? bestSelector(actionable[0]) : '';
} catch (e) { selectorValid = false; }
const target = norm(arg).toLowerCase();
const SEL = 'button, a, [role="button"], [role="link"], [role="tab"], [role="menuitem"], input[type="button"], input[type="submit"], label, [onclick]';
const describe = (el) => ({ tag: el.tagName.toLowerCase(), text: norm(el.textContent), selector: bestSelector(el) });
const gather = (pool) => {
  const vis = pool.filter(isVisible);
  return {
    exact: dropAncestors(vis.filter((el) => norm(el.textContent).toLowerCase() === target)),
    sub: dropAncestors(vis.filter((el) => norm(el.textContent).toLowerCase().includes(target))),
  };
};
let m = gather(Array.from(document.querySelectorAll(SEL)));
if (m.exact.length === 0 && m.sub.length === 0) {
  const pointer = Array.from(document.querySelectorAll('body *')).filter((el) => window.getComputedStyle(el).cursor === 'pointer');
  m = gather(pointer);
}
return { selectorValid, selectorCount, selectorVisibleCount, selectorTarget, exact: m.exact.map(describe), substring: m.sub.map(describe) };
"""

FILL_JS = r"""
const FILLABLE = 'input:not([type="button"]):not([type="submit"]):not([type="checkbox"]):not([type="radio"]):not([type="hidden"]), textarea, select, [contenteditable=""], [contenteditable="true"]';
let selectorValid = true, selectorCount = 0, selectorVisibleCount = 0, selectorTarget = '';
try {
  const matches = Array.from(document.querySelectorAll(arg)).filter((el) => el.matches(FILLABLE));
  selectorCount = matches.length;
  const actionable = matches.filter((el) => isVisible(el) && isEnabled(el));
  selectorVisibleCount = actionable.length;
  selectorTarget = actionable.length ? bestSelector(actionable[0]) : '';
} catch (e) { selectorValid = false; }
const target = norm(arg).toLowerCase();
const labelsFor = (el) => {
  const labels = [];
  const add = (value) => { const label = norm(value); if (label && !labels.includes(label)) labels.push(label); };
  add(el.getAttribute('aria-label'));
  const ref = el.getAttribute('aria-labelledby');
  if (ref) { const l = document.getElementById(ref); if (l) add(l.textContent); }
  if (el.id) { const l = document.querySelector('label[for=' + JSON.stringify(el.id) + ']'); if (l) add(l.textContent); }
  const wrap = el.closest('label');
  if (wrap) add(wrap.textContent);
  add(el.getAttribute('placeholder'));
  return labels;
};
const withLabel = Array.from(document.querySelectorAll(FILLABLE)).filter(isVisible)
  .map((el) => ({ el, labels: labelsFor(el) })).filter((x) => x.labels.length);
const mk = (x) => ({ tag: x.el.tagName.toLowerCase(), text: x.label, selector: bestSelector(x.el) });
const exact = withLabel.map((x) => ({ ...x, label: x.labels.find((label) => label.toLowerCase() === target) })).filter((x) => x.label);
const sub = withLabel.map((x) => ({ ...x, label: x.labels.find((label) => label.toLowerCase().includes(target)) })).filter((x) => x.label);
return { selectorValid, selectorCount, selectorVisibleCount, selectorTarget, exact: exact.map(mk), substring: sub.map(mk) };
"""


def _classify(seat, argument, body_js):
    expression = f"((arg) => {{{HELPERS_JS}{body_js}}})('{js_string(argument)}')"
    return evaluate_json(seat, expression)


def _pick(argument, verdict, noun):
    """One match acts; zero or many is an error naming what to do next."""
    candidates = verdict["exact"] or verdict["substring"]
    if len(candidates) == 1:
        return candidates[0]["selector"]
    if not candidates:
        raise BrowserError(f"{noun}: nothing visible matching {argument!r} — try `snap`, or pass a CSS selector")
    lines = [f"{noun}: {len(candidates)} elements match {argument!r} — pick one by selector:"]
    for candidate in candidates:
        text = candidate["text"][:60]
        lines.append(f'  {candidate["tag"]}  "{text}"  {candidate["selector"]}')
    raise BrowserError("\n".join(lines))


def _target(seat, argument, body_js, noun):
    verdict = _classify(seat, argument, body_js)
    if verdict["selectorValid"] and verdict["selectorCount"] >= 1:
        if verdict["selectorVisibleCount"] < 1:
            raise BrowserError(f"{noun}: selector {argument!r} matched nothing visible and enabled")
        return verdict["selectorTarget"] or argument
    return _pick(argument, verdict, noun)


def click_target(seat, argument):
    return _target(seat, argument, CLICK_JS, "click")


def fill_target(seat, argument):
    return _target(seat, argument, FILL_JS, "fill")
