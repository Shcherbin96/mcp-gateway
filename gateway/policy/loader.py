from pathlib import Path

import yaml

from gateway.policy.schema import PolicyDocument


def load_policies(path: str | Path) -> PolicyDocument:
    raw = yaml.safe_load(Path(path).read_text())
    return PolicyDocument.model_validate(raw)
