import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / '..'))

def test_probe():
    mods = []
    try:
        import importlib; mods.append(importlib.import_module('lib.bloom_power_lib'))
    except BaseException as e:
        print('PROBE-LOAD lib/bloom_power_lib.py:', type(e).__name__, e)
    print('PROBE-EXPORTS', sum(1 for m in mods for k in dir(m) if not k.startswith('_')))
    import inspect
    def _args(g):
        try:
            return [None] * len([q for q in inspect.signature(g).parameters.values() if q.default is q.empty and q.kind in (q.POSITIONAL_ONLY, q.POSITIONAL_OR_KEYWORD)])
        except (TypeError, ValueError):
            return []
    cands = []
    for m in mods:
        f = getattr(m, 'entry_kind', None)
        if callable(f):
            cands.append(f)
            cands += [c.cell_contents for c in (getattr(f, '__closure__', None) or ()) if callable(c.cell_contents) and getattr(c.cell_contents, '__name__', None) == 'entry_kind']  # decorator without functools.wraps
        for k in dir(m):  # methods of a class defined in the module
            c = getattr(m, k, None)
            if isinstance(c, type) and c.__module__ == m.__name__ and callable(getattr(c, 'entry_kind', None)):
                try:
                    inst = c(*_args(c.__init__)[1:])
                    cands.append(getattr(inst, 'entry_kind'))
                except BaseException as e:
                    print('PROBE-CALL entry_kind:', type(e).__name__, e)
    if not cands:
        print('PROBE-NOCALL entry_kind')
    for f in cands:
        try:
            f(*_args(f))
        except BaseException as e:
            print('PROBE-CALL entry_kind:', type(e).__name__, e)
    raise AssertionError('probe')
