import json
from pathlib import Path

from backend.common.schema import ProductCreate, ProductOut, UserCreate, UserOut


MODELS = {
    "user_create": UserCreate,
    "user_out": UserOut,
    "product_create": ProductCreate,
    "product_out": ProductOut,
}


def test_public_contract_schemas_match_snapshots() -> None:
    """Public response schemas should stay stable unless intentionally changed."""
    snapshot_dir = Path(__file__).parent / "snapshots" / "contracts"

    for name, model in MODELS.items():
        snapshot_path = snapshot_dir / f"{name}.json"
        assert snapshot_path.exists(), f"Missing snapshot for {name}"

        expected = json.loads(snapshot_path.read_text(encoding="utf-8"))
        actual = model.model_json_schema()

        assert actual == expected, f"Schema snapshot mismatch for {name}"
