from pathlib import Path


def test_enterprise_packages_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    required_paths = [
        root / "backend" / "application",
        root / "backend" / "contracts",
        root / "backend" / "integrations",
        root / "backend" / "platform",
        root / "backend" / "infrastructure" / "persistence",
    ]
    for path in required_paths:
        assert path.exists(), path
