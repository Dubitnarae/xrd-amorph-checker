"""문헌 결정 구조(COD CIF)로 상 카드(phases.json의 선 목록)를 계산한다.

    pip install pymatgen        # 개발용 — 프로그램에는 필요 없음
    python tools/make_phase_cards.py > out/phase_cards.json

- 결정 구조: tools/cards/cod_<번호>.cif (Crystallography Open Database, 퍼블릭 도메인)
- 강도: pymatgen XRDCalculator(Cu Kα1, 원자 산란인자·로렌츠-편광·다중도 반영, 배향·흡수 보정 없음)
- 상대강도 MIN_REL 이상, 2θ 20–90° 선만 남긴다(약한 선이 많으면 우연 매칭만 늘어난다)
결과를 src/xrdcheck/data/phases.json에 옮길 때는 CARDS의 출처 문구를 함께 적는다.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

CARD_DIR = Path(__file__).parent / "cards"
MIN_REL = 8
CU_KA1 = 1.540598

# name, CIF, 바꿀 것(원소 치환·격자), 입방정 격자 범위(같은 구조형의 다른 조성)
CARDS = [
    {"name": "Fe2B", "cif": "cod_1511153.cif", "structure": "tetragonal I4/mcm",
     "source": "COD 1511153 (Aronsson 1968) 구조, 계산 강도"},
    {"name": "(Fe,Nb)23B6", "cif": "cod_1511609.cif", "structure": "cubic Fm-3m (Cr23C6형)",
     "cubic_a_range_A": [10.76, 10.82],
     "source": "COD 1511609 (Idzikowski 2003, a = 10.761 Å) 구조, 계산 강도. Nb 고용 τ상 a = 10.819 Å(COD 1510909, Hawig 1991)까지 범위"},
    {"name": "Fe3B(t)", "cif": "cod_9011823.cif", "structure": "tetragonal I-4 (Ni3P형, 준안정 bct-Fe3B)",
     "replace": {"Ni": "Fe", "P": "B"}, "lattice": [8.655, 8.655, 4.297], "d_scale_range": [0.992, 1.002],
     "source": "원자 위치는 Ni3P형 COD 9011823(Skala 2003)에서 Ni→Fe, P→B로 바꿈, 격자 a = 8.655, c = 4.297 Å(bct-Fe3B 문헌값). "
               "P4₂/n형 Fe3B와 달리 (311) 39.1°가 소멸 — 실측에도 39.1° 피크 없음. "
               "실측 피크가 0.1–0.25° 높은 쪽이라(Si·P 고용 수축 추정) d 배율 0.992–1.002 허용(2026-10-29)"},
    {"name": "Fe3C", "cif": "cod_2300061.cif", "structure": "orthorhombic Pnma (cementite)",
     "source": "COD 2300061 (Wood 2004) 구조, 계산 강도. C 함유 합금에서만 의미"},
    {"name": "Fe5PB2", "cif": "cod_1510698.cif", "structure": "tetragonal I4/mcm",
     "source": "COD 1510698 (Rundqvist 1962) 구조, 계산 강도. P 함유 합금에서만 의미"},
    {"name": "Fe2P", "cif": "cod_9012123.cif", "structure": "hexagonal P-62m",
     "source": "COD 9012123 (Carlsson 1973) 구조, 계산 강도. P 함유 합금에서만 의미"},
    {"name": "fcc(γ-Fe/Cu)", "cif": "cod_5000216.cif", "structure": "fcc",
     "cubic_a_range_A": [3.585, 3.620],
     "source": "fcc 구조(COD 5000216 Cu, Swanson 1953), 계산 강도. a 범위: γ-Fe(Ni)형 약 3.59 Å ~ Cu 3.615 Å. "
               "2026-10-29 실측에서 43.5°/50.7° 쌍이 a = 3.596 Å로 일치(γ-Fe형) — Cu(43.3°/50.4°)와는 0.25° 차이"},
]


def _structure(card: dict):
    from pymatgen.core import Lattice, Structure
    from pymatgen.io.cif import CifParser

    s = CifParser(str(CARD_DIR / card["cif"]), occupancy_tolerance=1.1).parse_structures(primitive=False)[0]
    if "replace" in card or "lattice" in card:
        rep = card.get("replace", {})
        lat = Lattice.from_parameters(*card["lattice"], 90, 90, 90) if "lattice" in card else s.lattice
        new = Structure(lat, [], [])
        for site in s:  # 혼합 자리는 가장 많은 원소 하나로(치환 뒤 같은 원소가 되면 하나만)
            el = max(site.species.items(), key=lambda kv: kv[1])[0].symbol
            new.append(rep.get(el, el), site.frac_coords)
        new.merge_sites(tol=0.05, mode="delete")
        s = new
    return s


def _hkl(hkls: list[dict]) -> str:
    h = hkls[0]["hkl"]
    if len(h) == 4:  # 육방정 (h k i l) → (h k l)
        h = (h[0], h[1], h[3])
    return "".join(str(abs(i)) for i in h)


def card_lines(card: dict) -> list[dict]:
    from pymatgen.analysis.diffraction.xrd import XRDCalculator

    p = XRDCalculator(wavelength=CU_KA1).get_pattern(_structure(card), two_theta_range=(20, 90))
    out = []
    for y, hkls, d in zip(p.y, p.hkls, p.d_hkls):
        if y >= MIN_REL:
            ln = {"hkl": _hkl(hkls), "rel": int(round(y))}
            if "cubic_a_range_A" not in card:
                ln = {"hkl": ln["hkl"], "d_A": round(float(d), 5), "rel": ln["rel"]}
            out.append(ln)
    return out


def main() -> int:
    warnings.filterwarnings("ignore")
    phases = []
    for card in CARDS:
        ph = {"name": card["name"], "structure": card["structure"], "role": "secondary", "source": card["source"]}
        if "cubic_a_range_A" in card:
            ph["cubic_a_range_A"] = card["cubic_a_range_A"]
        if "d_scale_range" in card:
            ph["d_scale_range"] = card["d_scale_range"]
        ph["lines"] = card_lines(card)
        ph["systems"] = ["Fe"]
        phases.append(ph)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(phases, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
