from pathlib import Path

from eidolon_v16.language.spec import MacroTemplate, PatchSpec
from eidolon_v16.language.store import read_patch_bundle, save_patch_bundle


def test_language_bundle_io(tmp_path: Path) -> None:
    spec = PatchSpec(
        name="macro-test",
        version="0.1",
        created_ts_utc="2024-06-01T12:00:00Z",
        scope="arith",
        macros={
            "double": MacroTemplate(
                params=["x"],
                body={
                    "type": "binop",
                    "op": "mul",
                    "left": {"type": "var", "name": "x"},
                    "right": {"type": "int_const", "value": 2},
                },
            )
        },
    )
    bundle_dir = save_patch_bundle(spec, tmp_path / "language")
    loaded = read_patch_bundle(bundle_dir)
    assert loaded == spec
