"""app.text.norm_alias must equal the pipeline's norm_alias, which produced every alias_norm in the database."""

import csv
import importlib.util
from pathlib import Path

import pytest

from app.text import compact, norm_alias, tokens

ROOT = Path(__file__).resolve().parents[2]


def pipeline_norm_alias():
    path = ROOT / "data_pipeline" / "check_menu_templates.py"
    if not path.exists():
        pytest.skip("data_pipeline not present (deployed backend only)")
    spec = importlib.util.spec_from_file_location("pipeline_check_menu_templates", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.norm_alias


def all_real_aliases() -> list[str]:
    out = []
    with (ROOT / "data" / "reference" / "dish_catalogue.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            out += [row["name"], *row["aliases"].split(";")]
    with (ROOT / "data" / "reference" / "localities.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            out += [row["display_name"], *row["aliases"].split(";")]
    return [a for a in out if a.strip()]


def test_norm_alias_matches_the_pipeline_on_every_real_alias():
    theirs = pipeline_norm_alias()
    aliases = all_real_aliases()
    assert len(aliases) > 2000                     # dishes + aliases + areas; guards against reading nothing
    mismatches = [a for a in aliases if norm_alias(a) != theirs(a)]
    assert mismatches == []


def test_telugu_combining_marks_survive():
    assert norm_alias("కోడి బిర్యానీ") == "కోడి బిర్యానీ"


@pytest.mark.parametrize("a, b", [("McDonald's", "mc donalds"), ("Domino's", "dominos"), ("Banjara Hills", "banjarahills"),
                                  ("  KFC ", "kfc"), ("Hotel & Bar", "hotel and bar")])
def test_compact_forms_agree(a, b):
    assert compact(a) == compact(b)


def test_apostrophes_do_not_split_words():
    assert tokens("Domino's Pizza") == ["dominos", "pizza"]
