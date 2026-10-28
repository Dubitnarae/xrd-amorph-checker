"""공통 데이터 구조."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
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
