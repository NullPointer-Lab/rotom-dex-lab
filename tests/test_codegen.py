import pytest

from bridge.codegen import (
    CodegenError,
    apply_edits,
    commit_all,
    ensure_repo,
    list_versions,
    parse_edits,
    restore_version,
)

SAMPLE = """Claro! Vou deixar o texto novo.

ARQUIVO: ZappRobotFinal.ino
<<<<<<< BUSCAR
centerText("Oi Davi", 64, 2, ST77XX_WHITE);
=======
centerText("Ola Davi!", 64, 2, ST77XX_WHITE);
>>>>>>> SUBSTITUIR
"""


# --- parsing ----------------------------------------------------------------

def test_parse_single_block():
    edits = parse_edits(SAMPLE)
    assert len(edits) == 1
    assert edits[0]["file"] == "ZappRobotFinal.ino"
    assert 'Oi Davi' in edits[0]["search"]
    assert 'Ola Davi!' in edits[0]["replace"]


def test_parse_multiple_blocks():
    text = SAMPLE + """
ARQUIVO: ZappRobotFinal.ino
<<<<<<< BUSCAR
int brilho = 0;
=======
int brilho = 60;
>>>>>>> SUBSTITUIR
"""
    assert len(parse_edits(text)) == 2


def test_parse_none_when_no_blocks():
    assert parse_edits("Não entendi, pode explicar melhor?") == []


# --- applying ---------------------------------------------------------------

def test_apply_replace_unique(tmp_path):
    f = tmp_path / "ZappRobotFinal.ino"
    f.write_text('centerText("Oi Davi", 64, 2, ST77XX_WHITE);\n', encoding="utf-8")
    result = apply_edits(tmp_path, parse_edits(SAMPLE))
    assert result.applied and not result.failed
    assert 'Ola Davi!' in f.read_text(encoding="utf-8")


def test_apply_reports_when_not_found(tmp_path):
    f = tmp_path / "ZappRobotFinal.ino"
    f.write_text("nada a ver aqui\n", encoding="utf-8")
    result = apply_edits(tmp_path, parse_edits(SAMPLE))
    assert not result.applied and result.failed
    assert "não achei" in result.failed[0].lower()


def test_apply_ambiguous_match_is_skipped(tmp_path):
    f = tmp_path / "ZappRobotFinal.ino"
    f.write_text("dup\ndup\n", encoding="utf-8")
    edits = [{"file": "ZappRobotFinal.ino", "search": "dup", "replace": "x"}]
    result = apply_edits(tmp_path, edits)
    assert not result.applied and result.failed
    assert f.read_text(encoding="utf-8") == "dup\ndup\n"  # unchanged


def test_apply_creates_file_on_empty_search(tmp_path):
    edits = [{"file": "novo.ino", "search": "", "replace": "void setup(){}\n"}]
    result = apply_edits(tmp_path, edits)
    assert result.applied
    assert (tmp_path / "novo.ino").read_text(encoding="utf-8") == "void setup(){}\n"


def test_apply_rejects_path_traversal(tmp_path):
    edits = [{"file": "../escapou.ino", "search": "", "replace": "x"}]
    result = apply_edits(tmp_path, edits)
    assert not result.applied and result.failed
    assert not (tmp_path.parent / "escapou.ino").exists()


# --- git versioning ---------------------------------------------------------

def test_commit_list_and_restore(tmp_path):
    f = tmp_path / "ZappRobotFinal.ino"
    ensure_repo(tmp_path)

    f.write_text("VERSAO A\n", encoding="utf-8")
    h1 = commit_all(tmp_path, "Save A")
    assert h1

    f.write_text("VERSAO B\n", encoding="utf-8")
    h2 = commit_all(tmp_path, "Save B")
    assert h2 and h2 != h1

    # nothing changed -> no new save
    assert commit_all(tmp_path, "vazio") is None

    versions = list_versions(tmp_path)
    assert [v["message"] for v in versions] == ["Save B", "Save A"]
    assert versions[0]["current"] is True
    save_a = versions[1]["hash"]

    # restore the older version as a new save (non-destructive)
    info = restore_version(tmp_path, save_a)
    assert info["newSave"]
    assert f.read_text(encoding="utf-8") == "VERSAO A\n"
    after = list_versions(tmp_path)
    assert len(after) == 3  # Save A, Save B, + the restore save
    assert after[0]["current"] is True


def test_restore_rejects_bad_hash(tmp_path):
    ensure_repo(tmp_path)
    (tmp_path / "f.ino").write_text("x\n", encoding="utf-8")
    commit_all(tmp_path, "init")
    with pytest.raises(CodegenError):
        restore_version(tmp_path, "zzzz")
