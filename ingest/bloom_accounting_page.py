"""The ledger home page as Python-built HTML: no external assets, one inline style block and one inline script.

Bookkeeping view, not tax advice."""


def style_block():
    return """<style>
:root {
  --paper: #e9efec; --card: #f6f9f7; --ink: #12211d; --muted: #4d625b; --rule: #a9bbb4; --bad: #9b2c2c;
  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Charter, Georgia, serif;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 16px/1.5 var(--serif); }
h1, h2 { margin: 0; font-weight: 600; }
h1 { font-size: 2.1rem; line-height: 1.15; letter-spacing: -.01em; }
h2 { font-size: 1.25rem; }
a { color: var(--ink); text-underline-offset: .2em; }
main { max-width: 64rem; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
.top { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .25rem 1rem; }
.top nav a { font-size: 1rem; padding: .35rem 0; display: inline-block; }
.banner[hidden] { display: none; }
.picker { display: flex; flex-wrap: wrap; gap: .25rem 1rem; margin-top: .75rem; }
.picker select { font: inherit; font-size: 1.25rem; font-weight: 600; color: var(--ink); background: var(--card);
                 border: 2px solid var(--ink); border-radius: 0; padding: .3rem .6rem; min-height: 2.75rem; }
dl.figures { display: grid; grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr)); gap: 1rem; margin: 1rem 0; }
dl.figures dt { font-weight: 600; }
table { width: 100%; border-collapse: collapse; }
caption { text-align: left; padding: .6rem 1rem; color: var(--muted); font-size: .9rem; }
thead th { text-align: left; font-weight: 400; font-size: .8rem; letter-spacing: .06em; text-transform: uppercase;
           color: var(--muted); padding: .4rem 1rem; border-bottom: 1px solid var(--ink); }
tbody th, tbody td { text-align: left; padding: .55rem 1rem; border-bottom: 1px solid var(--rule); }
td.num, th.num { text-align: right; }
tr.voided td { text-decoration: line-through; color: var(--muted); }
.notset { color: var(--bad); }
a:focus-visible, select:focus-visible { outline: 3px solid var(--ink); outline-offset: 2px; }
@media (max-width: 40rem) {
  main { padding: 1.5rem .75rem 3rem; }
  .top { gap: .15rem .5rem; }
  .picker { gap: .15rem .5rem; }
  dl.figures { grid-template-columns: 1fr; }
  tbody tr { display: grid; grid-template-columns: 1.6fr 1fr 1fr; gap: 0 .5rem; }
  td.num { text-align: left; }
}
@media (prefers-reduced-motion: no-preference) {
  .picker select { transition: background .12s; }
}
</style>"""
