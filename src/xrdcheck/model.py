"""공통 데이터 구조."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np

# 파장 정보가 없는 파일(일반 2열 텍스트)에 쓰는 Cu Kα 기본값
CU_KALPHA1_A = 1.540598
CU_KALPHA2_A = 1.544426
CU_KALPHA2_RATIO = 0.5


@dataclass
class Pattern:
    """한 번의 XRD 측정. 강도는 항상 counts(포아송 가중치 기준) 단위로 보관한다."""

    two_theta: np.ndarray = field(repr=False)
    counts: np.ndarray = field(repr=False)
    source_path: Path
    file_format: str  # "xrdml" | "xpert_csv" | "generic_xy"
    sample_name: str
    kalpha1_A: float = CU_KALPHA1_A
    kalpha2_A: float | None = CU_KALPHA2_A
    kalpha2_ratio: float | None = CU_KALPHA2_RATIO
    counting_time_s: float | None = None
    file_timestamp_raw: str = ""  # 파일 내부 측정일시(장비 시계 — 측정일로 쓰지 않음)
    measurement_date: dt.date | None = None
    date_source: str = ""  # "파일명" | "폴더 경로" | "사용자 입력" | ""
    meta: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def n_points(self) -> int:
        return len(self.two_theta)

    @property
    def step_deg(self) -> float:
        return float(np.median(np.diff(self.two_theta)))

    @property
    def max_counts(self) -> float:
        return float(self.counts.max())

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)


class Verdict(str, Enum):
    AMORPHOUS = "비정질"
    SUSPECT = "결정상 의심"
    DETECTED = "결정상 검출"
    UNDETERMINED = "판정 불가"


@dataclass
class HaloFit:
    """배경 + 주/제2 halo 피팅 결과."""

    params: np.ndarray = field(repr=False)
    param_names: list[str] = field(repr=False)
    mu: np.ndarray = field(repr=False)  # 전체 2θ에서의 모델값
    components: dict[str, np.ndarray] = field(repr=False)  # "배경", "주 halo", "제2 halo"
    chi2_red: float
    bic: float
    n_used: int
    center: float
    fwhm_left: float
    fwhm_right: float
    d_A: float
    q_invA: float
    r1_A: float
    second_center: float | None = None
    second_fwhm: float | None = None

    @property
    def fwhm(self) -> float:
        return (self.fwhm_left + self.fwhm_right) / 2

    def param(self, name: str) -> float:
        return float(self.params[self.param_names.index(name)])


@dataclass
class Peak:
    """협폭(결정) 피크 후보."""

    two_theta: float
    z: float
    height: float  # counts (국소 pseudo-Voigt 높이)
    fwhm: float
    area: float
    level: str  # "검출"(z ≥ 검출 기준) | "의심"
    refined: bool = True  # 국소 피팅 성공 여부(실패하면 z로 추정한 값)
    eta: float = 0.5  # pseudo-Voigt 로렌츠 비율
    matches: list[str] = field(default_factory=list)  # 예: ["α-Fe(110)"]
    match_confidence: str = ""  # "높음" | "낮음" | ""
    satellite_of: float | None = None  # 더 강한 피크의 Kα2·꼬리로 판단되면 그 피크의 2θ
    notes: list[str] = field(default_factory=list)

    @property
    def counted(self) -> bool:
        """판정에 세는 피크인지(Kα2·꼬리는 별도 피크로 세지 않음)."""
        return self.satellite_of is None

    @property
    def significant(self) -> bool:
        return self.level == "검출"


@dataclass
class AnalysisResult:
    pattern: Pattern
    settings: dict = field(repr=False)
    version: str
    analyzed_at: dt.datetime
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)
    sentence: str = ""
    halo: HaloFit | None = None
    z: np.ndarray | None = field(default=None, repr=False)
    z_max: float | None = None
    z_max_at: float | None = None
    p_chance: float | None = None
    peaks: list[Peak] = field(default_factory=list)
    detection_limits: list[dict] = field(default_factory=list)  # {"label", "two_theta", "counts"}
    dl_curve: np.ndarray | None = field(default=None, repr=False)  # 2θ별 검출한계(counts)
    fit_mask: np.ndarray | None = field(default=None, repr=False)  # halo 피팅에 쓴 점(True)
    refit_rounds: int = 0
    broad: dict | None = None
    phase_lines: list[dict] = field(default_factory=list, repr=False)  # 그래프용 상 기준선
    warnings: list[str] = field(default_factory=list)

    @property
    def counted_peaks(self) -> list[Peak]:
        return [p for p in self.peaks if p.counted]
