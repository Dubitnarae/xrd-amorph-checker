"""Phase 2: 가상 피크 주입 시험(기대값 JSON의 injection_tests)."""

import copy
import json

import pytest
from conftest import EXPECTED, SAMPLE_STEM, SAMPLES

from xrdcheck.analysis.pipeline import analyze
from xrdcheck.analysis.profiles import gaussian
from xrdcheck.io import load_pattern


@pytest.fixture(scope="module")
def base_pattern():
    path = SAMPLES / f"{SAMPLE_STEM}.xrdml"
    if not path.exists():
        pytest.skip("샘플 파일 없음")
    return load_pattern(path)


def _cases():
    path = EXPECTED / f"{SAMPLE_STEM}.json"
    if not path.exists():
        return []
    inj = json.loads(path.read_text(encoding="utf-8"))["injection_tests"]
    return [pytest.param(c.get("fwhm_deg", inj["fwhm_deg"]), c,
                         id=" + ".join(f"{a}:{h}" for a, h in c["inject"]) + f" w{c.get('fwhm_deg', inj['fwhm_deg'])}")
            for c in inj["cases"]]


@pytest.mark.parametrize("fwhm, case", _cases())
def test_injection(base_pattern, fwhm, case):
    p = copy.deepcopy(base_pattern)
    for tt, h in case["inject"]:  # 노이즈 없이 기대값 그대로 더함(재현성)
        p.counts = p.counts + gaussian(p.two_theta, h, tt, fwhm)
    r = analyze(p)
    assert r.verdict.value == case["expect_verdict"], r.sentence
    if "expect_match" in case:
        found = {m for pk in r.counted_peaks for m in pk.matches}
        assert set(case["expect_match"]) <= found
    # 높이는 여기서 확인하지 않는다: 주입 피크는 Kα2가 없는 단일선이라, Kα1+Kα2 쌍으로 다듬으면
    # 높이가 낮게 나온다(실측에는 Kα2가 있음). 높이 확인은 test_analysis의 Kα2 쌍 합성 시험에서 한다.
