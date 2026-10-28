"""판정 규칙 v1."""

from __future__ import annotations

from xrdcheck.model import Peak, Verdict


def decide(peaks: list[Peak]) -> tuple[Verdict, list[str]]:
    """
    - 결정상 검출: 검출 기준 이상 피크가 있고, 라이브러리와 매칭되거나 그런 피크가 2개 이상
    - 결정상 의심: 의심 구간 피크가 있거나, 매칭되지 않는 검출 기준 이상 단일 피크
    - 비정질: 위 어디에도 해당하지 않음
    (판정 불가는 품질 점검·피팅 단계에서 정한다.)
    """
    counted = [p for p in peaks if p.counted]
    sig = [p for p in counted if p.significant]
    sus = [p for p in counted if not p.significant]
    matched = [p for p in sig if p.accepted_match]
    if sig and (matched or len(sig) >= 2):
        reasons = []
        if matched:
            reasons.append("검출 기준 이상 피크가 상 라이브러리와 매칭됨: "
                           + ", ".join(f"{p.two_theta:.2f}° {'/'.join(p.matches)}" for p in matched))
        if len(sig) >= 2:
            reasons.append(f"검출 기준 이상 피크 {len(sig)}개")
        return Verdict.DETECTED, reasons
    if sig or sus:
        reasons = []
        if sig:
            pk = sig[0]
            why = "최강선이 보이지 않아 매칭 불인정" if pk.matches else "라이브러리와 매칭되지 않음"
            reasons.append(f"검출 기준 이상 단일 피크({pk.two_theta:.2f}°{' ' + '/'.join(pk.matches) if pk.matches else ''}) — {why}")
        if sus:
            reasons.append("의심 구간 피크: " + ", ".join(f"{p.two_theta:.2f}°(z {p.z:.1f})" for p in sus))
        return Verdict.SUSPECT, reasons
    return Verdict.AMORPHOUS, ["의심 기준 이상의 협폭 피크 없음"]
