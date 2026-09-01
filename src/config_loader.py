"""
config_loader.py

Loads dataset_config.yaml so the rest of the pipeline never hardcodes
a column name. To point this pipeline at a different dataset, edit
config/dataset_config.yaml only - no code changes needed.
"""

import yaml
from pathlib import Path


def load_config(config_path: str = "config/dataset_config.yaml") -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found at {path.resolve()}. "
            "Run this script from the project root, or pass --config with the right path."
        )
    with open(path, "r") as f:
        config = yaml.safe_load(f)
    return config
