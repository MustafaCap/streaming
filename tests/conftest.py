import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def gecici_veri_klasoru(tmp_path, monkeypatch):
    """Testler gerçek %APPDATA% klasörüne dokunmasın."""
    monkeypatch.setenv("YAYIN_VERI_KLASORU", str(tmp_path / "veri"))
    return tmp_path / "veri"
