from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from constants import (
        DEFAULT_CC_INTERP,
        DEFAULT_SMOOTHING_MODE,
        MIDI_MAX,
        MIDI_MIN,
        MIN_CC_STEP_Q,
        QUARTERS_PER_WHOLE,
        SUSTAIN_PEDAL_ON_DELAY_Q,
        SUSTAIN_PEDAL_ON_THRESHOLD,
        SUSTAIN_PEDAL_VALUE_OFF,
    )
    from utils import clamp
except ImportError:
    from .constants import (
        DEFAULT_CC_INTERP,
        DEFAULT_SMOOTHING_MODE,
        MIDI_MAX,
        MIDI_MIN,
        MIN_CC_STEP_Q,
        QUARTERS_PER_WHOLE,
        SUSTAIN_PEDAL_ON_DELAY_Q,
        SUSTAIN_PEDAL_ON_THRESHOLD,
        SUSTAIN_PEDAL_VALUE_OFF,
    )
    from .utils import clamp


def catmull_rom(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        (2 * p1)
        + (-p0 + p2) * t
        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
        + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
    )


def eval_curve_at(
    breakpoints: List[Dict[str, float]],
    interp: str,
    t: float,
) -> float:
    if not breakpoints:
        return 0.0
    if len(breakpoints) == 1:
        return breakpoints[0]["value"]
    idx = 0
    while idx < len(breakpoints) - 1 and breakpoints[idx + 1]["time_q"] <= t:
        idx += 1
    if idx >= len(breakpoints) - 1:
        return breakpoints[-1]["value"]
    p1 = breakpoints[idx]
    p2 = breakpoints[idx + 1]
    if interp == "hold":
        return p1["value"]
    if p2["time_q"] <= p1["time_q"]:
        return p2["value"]
    u = (t - p1["time_q"]) / (p2["time_q"] - p1["time_q"])
    if interp == "linear":
        return p1["value"] + (p2["value"] - p1["value"]) * u
    p0 = breakpoints[idx - 1] if idx - 1 >= 0 else p1
    p3 = breakpoints[idx + 2] if idx + 2 < len(breakpoints) else p2
    return catmull_rom(p0["value"], p1["value"], p2["value"], p3["value"], u)


def dedupe_points(points: List[Dict[str, float]]) -> List[Dict[str, float]]:
    deduped: List[Dict[str, float]] = []
    for point in points:
        if deduped and deduped[-1]["time_q"] == point["time_q"]:
            deduped[-1] = point
        else:
            deduped.append(point)
    return deduped


def build_hold_cc_events(
    points: List[Dict[str, float]],
    cc_num: int,
    length_q: float,
    default_chan: int,
) -> List[Dict[str, Any]]:
    if not points:
        return []

    dedup = dedupe_points(points)

    events: List[Dict[str, Any]] = []
    last_val: Optional[int] = None

    def add_event(time_q: float, value: float) -> None:
        nonlocal last_val
        t = clamp(float(time_q), 0.0, max(0.0, length_q))
        v = int(round(clamp(float(value), float(MIDI_MIN), float(MIDI_MAX))))
        if last_val is None or v != last_val:
            events.append({"time_q": t, "cc": cc_num, "value": v, "chan": default_chan})
            last_val = v

    add_event(0.0, dedup[0]["value"])
    for point in dedup:
        add_event(point["time_q"], point["value"])

    return events


def build_sustain_pedal_cc_events(
    points: List[Dict[str, float]],
    cc_num: int,
    length_q: float,
    default_chan: int,
) -> List[Dict[str, Any]]:
    if not points:
        return []

    dedup = dedupe_points(points)

    segments: List[Dict[str, float]] = []
    for point in dedup:
        if not segments or segments[-1]["value"] != point["value"]:
            segments.append(point)

    if not segments:
        return []

    events: List[Dict[str, Any]] = []
    last_val: Optional[int] = None

    def add_event(time_q: float, value_int: int) -> None:
        nonlocal last_val
        t = clamp(float(time_q), 0.0, max(0.0, length_q))
        v = int(clamp(int(value_int), MIDI_MIN, MIDI_MAX))
        if last_val is None or v != last_val:
            events.append({"time_q": t, "cc": cc_num, "value": v, "chan": default_chan})
            last_val = v

    start_val = int(round(segments[0]["value"]))
    if start_val >= SUSTAIN_PEDAL_ON_THRESHOLD and SUSTAIN_PEDAL_ON_DELAY_Q > 0:
        add_event(0.0, SUSTAIN_PEDAL_VALUE_OFF)
        next_time = segments[1]["time_q"] if len(segments) > 1 else (length_q + 1.0)
        shifted = segments[0]["time_q"] + SUSTAIN_PEDAL_ON_DELAY_Q
        add_event(shifted if shifted < next_time else segments[0]["time_q"], start_val)
    else:
        add_event(0.0, start_val)

    prev_val = start_val
    for idx in range(1, len(segments)):
        time_q = segments[idx]["time_q"]
        value = int(round(segments[idx]["value"]))
        is_rising = prev_val < SUSTAIN_PEDAL_ON_THRESHOLD and value >= SUSTAIN_PEDAL_ON_THRESHOLD
        if is_rising and SUSTAIN_PEDAL_ON_DELAY_Q > 0:
            next_time = segments[idx + 1]["time_q"] if idx + 1 < len(segments) else (length_q + 1.0)
            shifted = time_q + SUSTAIN_PEDAL_ON_DELAY_Q
            if shifted < next_time:
                time_q = shifted
        add_event(time_q, value)
        prev_val = value

    return events


def build_cc_events(
    curves: Dict[str, Any],
    profile: Dict[str, Any],
    length_q: float,
    default_chan: int,
) -> List[Dict[str, Any]]:
    controller_cfg = profile.get("controllers", {})
    semantic_to_cc = controller_cfg.get("semantic_to_cc", {})
    smoothing = controller_cfg.get("smoothing", {})
    step_q = parse_step_q(smoothing.get("min_step", "1/64"))
    interp_default = smoothing.get("interp", DEFAULT_CC_INTERP)
    mode = smoothing.get("mode", DEFAULT_SMOOTHING_MODE)
    write_every_step = bool(smoothing.get("write_every_step", True))

    events: List[Dict[str, Any]] = []
    if not curves:
        return events

    for semantic, curve in curves.items():
        if semantic not in semantic_to_cc:
            continue
        cc_num = int(semantic_to_cc[semantic])
        if cc_num < MIDI_MIN or cc_num > MIDI_MAX:
            continue
        interp = str(curve.get("interp") or interp_default).lower()
        raw_points = curve.get("breakpoints", [])
        points: List[Dict[str, float]] = []
        for point in raw_points:
            try:
                time_q = float(point.get("time_q", 0.0))
                value = float(point.get("value", 0.0))
            except (TypeError, ValueError):
                continue
            time_q = clamp(time_q, 0.0, max(0.0, length_q))
            value = clamp(value, float(MIDI_MIN), float(MIDI_MAX))
            points.append({"time_q": time_q, "value": value})
        if not points:
            continue
        points.sort(key=lambda p: p["time_q"])

        if interp == "hold":
            if semantic == "sustain_pedal":
                events.extend(build_sustain_pedal_cc_events(points, cc_num, length_q, default_chan))
            else:
                events.extend(build_hold_cc_events(points, cc_num, length_q, default_chan))
            continue

        time_q = 0.0
        last_val: Optional[int] = None
        while time_q <= length_q + 1e-6:
            value = eval_curve_at(points, interp, time_q)
            value_int = int(round(clamp(value, float(MIDI_MIN), float(MIDI_MAX))))
            if mode == "fixed" or write_every_step:
                events.append(
                    {
                        "time_q": time_q,
                        "cc": cc_num,
                        "value": value_int,
                        "chan": default_chan,
                    }
                )
            else:
                if last_val is None or value_int != last_val:
                    events.append(
                        {
                            "time_q": time_q,
                            "cc": cc_num,
                            "value": value_int,
                            "chan": default_chan,
                        }
                    )
            last_val = value_int
            time_q += step_q
    return events


def parse_step_q(step: Any) -> float:
    if isinstance(step, (int, float)):
        return max(MIN_CC_STEP_Q, float(step))
    if isinstance(step, str) and "/" in step:
        parts = step.split("/", 1)
        try:
            num = float(parts[0])
            den = float(parts[1])
            if den > 0:
                return max(MIN_CC_STEP_Q, (QUARTERS_PER_WHOLE * num) / den)
        except (ValueError, ZeroDivisionError):
            return MIN_CC_STEP_Q
    return MIN_CC_STEP_Q
