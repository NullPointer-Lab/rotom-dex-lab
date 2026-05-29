from bridge.libfix import known_library, missing_headers, pick_library_from_search


def test_missing_headers_parses_and_dedups():
    text = (
        "ZappRobotFinal.ino:1:10: fatal error: Adafruit_GFX.h: No such file or directory\n"
        "other line\n"
        "fatal error: src/TFT_RoboEyes.h: No such file or directory\n"
        "fatal error: Adafruit_GFX.h: No such file or directory\n"
    )
    assert missing_headers(text) == ["Adafruit_GFX.h", "TFT_RoboEyes.h"]


def test_missing_headers_none():
    assert missing_headers("tudo certo, sem erros") == []


def test_known_library():
    assert known_library("TFT_RoboEyes.h") == "TFT_RoboEyes"
    assert known_library("Adafruit_GFX.h") == "Adafruit GFX Library"
    assert known_library("naoexiste.h") is None


def test_pick_library_from_search_matches_include():
    s = (
        '{"libraries":[{"name":"Outra","provides_includes":["Outra.h"]},'
        '{"name":"TFT_RoboEyes","provides_includes":["TFT_RoboEyes.h"]}]}'
    )
    assert pick_library_from_search(s, "TFT_RoboEyes.h") == "TFT_RoboEyes"
    assert pick_library_from_search(s, "Nada.h") is None


def test_pick_library_handles_releases_shape():
    s = '{"libraries":[{"name":"Foo","releases":{"1.0.0":{"provides_includes":["Foo.h"]}}}]}'
    assert pick_library_from_search(s, "Foo.h") == "Foo"


def test_pick_library_bad_json():
    assert pick_library_from_search("nao e json", "x.h") is None
