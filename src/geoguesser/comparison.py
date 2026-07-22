from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def countries_match(prediction: Any, ground_truth: Any) -> bool:
    def normalize(value: Any) -> str:
        return " ".join(str(value or "").casefold().replace("-", " ").split())

    aliases = {
        "usa": "united states",
        "us": "united states",
        "united states of america": "united states",
        "uk": "united kingdom",
        "great britain": "united kingdom",
    }
    predicted = aliases.get(normalize(prediction), normalize(prediction))
    actual = aliases.get(normalize(ground_truth), normalize(ground_truth))
    return bool(predicted) and predicted == actual


def summarize_system(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = list(records)
    successful = [record for record in records if record.get("status") == "ok"]
    correct = sum(
        countries_match(record.get("prediction", {}).get("country"), record.get("ground_truth"))
        for record in successful
    )
    usage = [
        event
        for record in successful
        for event in record.get("usage", [])
        if isinstance(event, Mapping)
    ]
    total_cost = sum(float(event.get("cost_usd", 0) or 0) for event in usage)
    attempted = len(records)
    input_tokens = sum(int(event.get("input_tokens", 0) or 0) for event in usage)
    output_tokens = sum(int(event.get("output_tokens", 0) or 0) for event in usage)
    reasoning_tokens = sum(int(event.get("reasoning_tokens", 0) or 0) for event in usage)
    return {
        "attempted": attempted,
        "succeeded": len(successful),
        "correct": correct,
        "accuracy": correct / attempted if attempted else 0.0,
        "success_rate": len(successful) / attempted if attempted else 0.0,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": input_tokens + output_tokens + reasoning_tokens,
        "image_tokens": sum(int(event.get("image_tokens", 0) or 0) for event in usage),
        "cost_usd": total_cost,
        "mean_cost_usd": total_cost / attempted if attempted else 0.0,
        "cost_per_correct_usd": total_cost / correct if correct else None,
    }


def comparison_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    claude_records = []
    mas_records = []
    paired = []
    for row in rows:
        ground_truth = row.get("ground_truth")
        claude = {**row.get("claude", {}), "ground_truth": ground_truth}
        mas = {**row.get("mas", {}), "ground_truth": ground_truth}
        claude_records.append(claude)
        mas_records.append(mas)
        if claude.get("status") == "ok" and mas.get("status") == "ok":
            paired.append((ground_truth, claude, mas))
    claude_summary = summarize_system(claude_records)
    mas_summary = summarize_system(mas_records)
    paired_count = len(paired)
    paired_claude = sum(
        countries_match(item[1].get("prediction", {}).get("country"), item[0]) for item in paired
    )
    paired_mas = sum(
        countries_match(item[2].get("prediction", {}).get("country"), item[0]) for item in paired
    )
    claude_cost = claude_summary["cost_usd"]
    mas_cost = mas_summary["cost_usd"]
    return {
        "rows": len(rows),
        "claude_opus": claude_summary,
        "mas": mas_summary,
        "paired": {
            "count": paired_count,
            "claude_accuracy": paired_claude / paired_count if paired_count else 0.0,
            "mas_accuracy": paired_mas / paired_count if paired_count else 0.0,
            "mas_accuracy_delta_points": (
                100 * (paired_mas - paired_claude) / paired_count if paired_count else 0.0
            ),
        },
        "cost_comparison": {
            "mas_vs_claude_ratio": mas_cost / claude_cost if claude_cost else None,
            "mas_savings_percent": (
                100 * (1 - mas_cost / claude_cost) if claude_cost else None
            ),
        },
    }
