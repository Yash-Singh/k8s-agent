"""Built-in Kubernetes log samples for testing and demonstration."""

from pathlib import Path
from typing import Dict

SAMPLES_DIR = Path(__file__).parent


def get_available_samples() -> Dict[str, Path]:
    """Return dictionary of available sample log file paths."""
    samples = {}
    for p in SAMPLES_DIR.glob("*.log"):
        samples[p.stem] = p
    return samples


def get_sample_log(name: str) -> str:
    """Retrieve content of a specific sample log."""
    path = SAMPLES_DIR / f"{name}.log"
    if not path.exists():
        raise FileNotFoundError(f"Sample log '{name}' not found. Available: {list(get_available_samples().keys())}")
    return path.read_text(encoding="utf-8")
