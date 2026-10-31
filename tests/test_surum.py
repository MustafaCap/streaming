"""Sürüm numarası ve değişiklik listesi birbirini tutmalı (Releases notu buradan gelir)."""

import importlib.util
import re
from pathlib import Path

import pytest

from core.surum import SURUM

KOK = Path(__file__).resolve().parent.parent


def _betik():
    spec = importlib.util.spec_from_file_location("surum_notu", KOK / "kurulum" / "surum_notu.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_surum_bicimi():
    assert re.fullmatch(r"\d+\.\d+\.\d+", SURUM)


def test_her_surumun_degisiklik_notu_var():
    notu = _betik().surum_notu(SURUM)
    assert notu.strip().startswith("- ") and "## " not in notu


def test_olmayan_surum_hata_verir():
    with pytest.raises(SystemExit):
        _betik().surum_notu("0.0.0")
