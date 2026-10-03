import sys
from pathlib import Path

# the corpus helpers live in tests/corpus (a package named corpus)
sys.path.insert(0, str(Path(__file__).parent / "tests"))
