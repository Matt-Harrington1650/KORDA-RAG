#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Calibrate strict caption/summary confidence thresholds by document class."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LabeledPoint:
    confidence: float
    is_correct: bool


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "pass", "correct"}:
            return True
        if lowered in {"false", "0", "no", "n", "fail", "incorrect"}:
            return False
    return None


def _extract_point(record: dict[str, Any], phase: str) -> tuple[float | None, bool | None]:
    phase_payload = record.get(phase, {})
    confidence = None
    correctness = None

    if isinstance(phase_payload, dict):
        confidence = phase_payload.get("confidence")
        correctness = phase_payload.get("is_correct")
        if correctness is None:
            correctness = phase_payload.get("ground_truth_correct")

    if confidence is None:
        confidence = record.get(f"{phase}_confidence")
    if correctness is None:
        correctness = record.get(f"{phase}_is_correct")
    if correctness is None:
        correctness = record.get(f"{phase}_ground_truth_correct")

    if confidence is None:
        return None, None
    try:
        confidence = float(confidence)
    except Exception:
        return None, None

    correctness = _parse_bool(correctness)
    return confidence, correctness


def _candidate_thresholds(points: list[LabeledPoint]) -> list[float]:
    candidates = sorted({round(p.confidence, 4) for p in points})
    if 0.0 not in candidates:
        candidates.insert(0, 0.0)
    return candidates


def _score_threshold(points: list[LabeledPoint], threshold: float) -> tuple[float, float, int]:
    selected = [p for p in points if p.confidence >= threshold]
    if not selected:
        return 0.0, 0.0, 0
    true_positive = sum(1 for p in selected if p.is_correct)
    precision = true_positive / len(selected)
    all_positive = sum(1 for p in points if p.is_correct)
    recall = true_positive / all_positive if all_positive > 0 else 0.0
    return precision, recall, len(selected)


def calibrate_phase(
    points_by_class: dict[str, list[LabeledPoint]],
    target_precision: float,
    min_samples: int,
) -> dict[str, Any]:
    recommendations: dict[str, Any] = {}
    for doc_class, points in sorted(points_by_class.items()):
        if len(points) < min_samples:
            recommendations[doc_class] = {
                "status": "insufficient_samples",
                "samples": len(points),
                "recommended_threshold": None,
            }
            continue

        best: tuple[float, float, float, int] | None = None
        for threshold in _candidate_thresholds(points):
            precision, recall, support = _score_threshold(points, threshold)
            if precision < target_precision:
                continue
            # Prefer better recall; tie-break by lower threshold (higher coverage).
            if best is None or recall > best[1] or (
                recall == best[1] and threshold < best[0]
            ):
                best = (threshold, recall, precision, support)

        if best is None:
            # Fallback to threshold with best precision, then best recall.
            fallback = max(
                (
                    (_score_threshold(points, t)[0], _score_threshold(points, t)[1], t, _score_threshold(points, t)[2])
                    for t in _candidate_thresholds(points)
                ),
                key=lambda x: (x[0], x[1], -x[2]),
            )
            recommendations[doc_class] = {
                "status": "target_not_met",
                "samples": len(points),
                "recommended_threshold": round(float(fallback[2]), 4),
                "estimated_precision": round(float(fallback[0]), 4),
                "estimated_recall": round(float(fallback[1]), 4),
                "selected_support": int(fallback[3]),
            }
        else:
            recommendations[doc_class] = {
                "status": "calibrated",
                "samples": len(points),
                "recommended_threshold": round(float(best[0]), 4),
                "estimated_precision": round(float(best[2]), 4),
                "estimated_recall": round(float(best[1]), 4),
                "selected_support": int(best[3]),
            }

    return recommendations


def load_points(input_jsonl: Path) -> tuple[dict[str, list[LabeledPoint]], dict[str, list[LabeledPoint]]]:
    caption_points: dict[str, list[LabeledPoint]] = defaultdict(list)
    summary_points: dict[str, list[LabeledPoint]] = defaultdict(list)

    for line in input_jsonl.read_text(encoding="utf-8").splitlines():
        row = line.strip()
        if not row:
            continue
        payload = json.loads(row)
        doc_class = str(
            payload.get("document_class")
            or payload.get("doc_class")
            or payload.get("artifact_type")
            or payload.get("document_type")
            or "unknown"
        ).lower()

        caption_conf, caption_correct = _extract_point(payload, "caption")
        if caption_conf is not None and caption_correct is not None:
            caption_points[doc_class].append(
                LabeledPoint(confidence=caption_conf, is_correct=caption_correct)
            )

        summary_conf, summary_correct = _extract_point(payload, "summary")
        if summary_conf is not None and summary_correct is not None:
            summary_points[doc_class].append(
                LabeledPoint(confidence=summary_conf, is_correct=summary_correct)
            )

    return caption_points, summary_points


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calibrate per-document-class strict confidence thresholds"
    )
    parser.add_argument(
        "--input-jsonl",
        required=True,
        help="Path to labeled calibration JSONL file",
    )
    parser.add_argument(
        "--output-json",
        default="docs/operations/calibration-threshold-recommendations.json",
        help="Output JSON report path",
    )
    parser.add_argument(
        "--target-precision",
        type=float,
        default=0.95,
        help="Target precision for calibrated thresholds",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=20,
        help="Minimum sample count per class to calibrate directly",
    )
    args = parser.parse_args()

    input_path = Path(args.input_jsonl)
    output_path = Path(args.output_json)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    caption_points, summary_points = load_points(input_path)
    report = {
        "input_jsonl": str(input_path),
        "target_precision": args.target_precision,
        "min_samples": args.min_samples,
        "caption_thresholds": calibrate_phase(
            caption_points, target_precision=args.target_precision, min_samples=args.min_samples
        ),
        "summary_thresholds": calibrate_phase(
            summary_points, target_precision=args.target_precision, min_samples=args.min_samples
        ),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
