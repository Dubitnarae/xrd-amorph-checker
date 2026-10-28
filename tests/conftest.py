import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
EXPECTED = ROOT / "tests" / "expected"


def _sample_stem() -> str:
    """실측 샘플 파일 이름(확장자 제외). 실제 시료명은 비공개라 tests/private/sample_stem.txt에만 둔다."""
    p = ROOT / "tests" / "private" / "sample_stem.txt"
    return p.read_text(encoding="utf-8").strip() if p.exists() else "SMP-01a-260910-001"


SAMPLE_STEM = _sample_stem()


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
def sample_stem():
    return SAMPLE_STEM


@pytest.fixture
def expected():
    path = EXPECTED / f"{SAMPLE_STEM}.json"
    if not path.exists():
        pytest.skip(f"기대값 파일 없음: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))
