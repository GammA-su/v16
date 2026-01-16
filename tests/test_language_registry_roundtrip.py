from pathlib import Path

from eidolon_v16.language.registry import LanguageRegistry
from eidolon_v16.language.spec import MacroTemplate, PatchSpec


def test_language_registry_roundtrip(tmp_path: Path) -> None:
    registry_path = tmp_path / "language" / "registry.json"
    spec = PatchSpec(
        name="macro-v1",
        version="1.0",
        created_ts_utc="2024-01-01T00:00:00Z",
        scope="arith",
        macros={
            "add_one": MacroTemplate(
                params=["x"],
                body={
                    "type": "binop",
                    "op": "add",
                    "left": {"type": "var", "name": "x"},
                    "right": {"type": "int_const", "value": 1},
                },
            )
        },
    )
    registry = LanguageRegistry.load(registry_path)
    bundle_dir = tmp_path / "bundle"
    registry.register(spec, bundle_dir)
    registry.save(registry_path)

    reloaded = LanguageRegistry.load(registry_path)
    record = reloaded.get_patch(spec.name)
    assert record is not None
    assert record.spec == spec
    assert record.bundle_dir == str(bundle_dir)
