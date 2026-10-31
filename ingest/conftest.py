import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parents[2] / "bin"))   # bloom_ledger.py / bloom_power_lib.py (copied to /app in the image)
