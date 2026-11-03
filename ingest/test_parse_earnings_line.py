import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / '..'))

def test_probe():
    mods = []
    try:
        import importlib; mods.append(importlib.import_module('ingest.bloom_accounting_index'))
    except BaseException as e:
        print('PROBE-LOAD ingest/bloom_accounting_index.py:', type(e).__name__, e)
    print('PROBE-EXPORTS', sum(1 for m in mods for k in dir(m) if not k.startswith('_')))
    import inspect
    def _args(g):
        try:
            return [None] * len([q for q in inspect.signature(g).parameters.values() if q.default is q.empty and q.kind in (q.POSITIONAL_ONLY, q.POSITIONAL_OR_KEYWORD)])
        except (TypeError, ValueError):
            return []
    cands = []
    for m in mods:
        f = getattr(m, 'parse_earnings_line', None)
        if callable(f):
            cands.append(f)
            cands += [c.cell_contents for c in (getattr(f, '__closure__', None) or ()) if callable(c.cell_contents) and getattr(c.cell_contents, '__name__', None) == 'parse_earnings_line']  # decorator without functools.wraps
        for k in dir(m):  # methods of a class defined in the module
            c = getattr(m, k, None)
            if isinstance(c, type) and c.__module__ == m.__name__ and callable(getattr(c, 'parse_earnings_line', None)):
                try:
                    inst = c(*_args(c.__init__)[1:])
                    cands.append(getattr(inst, 'parse_earnings_line'))
                except BaseException as e:
                    print('PROBE-CALL parse_earnings_line:', type(e).__name__, e)
    if not cands:
        print('PROBE-NOCALL parse_earnings_line')
    for f in cands:
        try:
            f(*_args(f))
        except BaseException as e:
            print('PROBE-CALL parse_earnings_line:', type(e).__name__, e)
    raise AssertionError('probe')
