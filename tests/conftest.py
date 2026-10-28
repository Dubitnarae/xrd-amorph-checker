import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
EXPECTED = ROOT / "tests" / "expected"
SAMPLE_STEM = "SMP-01a-260910-001"


@pytest.fixture
def sample_file():
    """샘플(실측) 파일 경로. 공개 저장소처럼 파일이 없으면 테스트를 건너뛴다."""

    def get(suffix: str) -> Path:
        path = SAMPLES / f"{SAMPLE_STEM}{suffix}"
        if not path.exists():
            pytest.skip(f"샘플 파일 없음: {path.name}")
        return path

    return get


@pytest.fixture
def expected():
    path = EXPECTED / f"{SAMPLE_STEM}.json"
    if not path.exists():
        pytest.skip(f"기대값 파일 없음: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))
