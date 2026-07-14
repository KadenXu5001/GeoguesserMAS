from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class Pricing:
    input_per_million: float
    output_per_million: float


GEMINI_FLASH = Pricing(input_per_million=0.50, output_per_million=3.00)
CLAUDE_OPUS = Pricing(input_per_million=5.00, output_per_million=25.00)


def claude_image_tokens(width: int, height: int) -> int:
    """Return visual patch tokens for an image that fits the native limits."""
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    return ceil(width / 28) * ceil(height / 28)


def token_cost(pricing: Pricing, input_tokens: int, output_tokens: int) -> float:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts cannot be negative")
    return (
        input_tokens * pricing.input_per_million
        + output_tokens * pricing.output_per_million
    ) / 1_000_000


FLASH_EXTRACTION = token_cost(GEMINI_FLASH, 600 + 4 * 1_120, 1_200)
FLASH_ORCHESTRATOR_DECISION = token_cost(GEMINI_FLASH, 2_400, 400)
FLASH_SPECIALIST = token_cost(GEMINI_FLASH, 2_000, 500)
FLASH_ORCHESTRATOR_FINAL = token_cost(GEMINI_FLASH, 3_200, 400)
FLASH_ORCHESTRATOR_REVIEW = token_cost(GEMINI_FLASH, 2_400, 400)
FLASH_REEXAMINATION = token_cost(GEMINI_FLASH, 300 + 1_120, 350)
OPUS_BASELINE = token_cost(
    CLAUDE_OPUS,
    600 + 4 * claude_image_tokens(1_024, 1_024),
    600,
)

PATHS = {
    "Opus direct baseline": OPUS_BASELINE,
    "MAS easy": FLASH_EXTRACTION + FLASH_ORCHESTRATOR_DECISION,
    "MAS delegated": (
        FLASH_EXTRACTION
        + FLASH_ORCHESTRATOR_DECISION
        + FLASH_SPECIALIST
        + FLASH_ORCHESTRATOR_FINAL
    ),
    "MAS hard": (
        FLASH_EXTRACTION
        + FLASH_ORCHESTRATOR_DECISION
        + FLASH_SPECIALIST
        + FLASH_ORCHESTRATOR_REVIEW
        + FLASH_ORCHESTRATOR_FINAL
        + FLASH_REEXAMINATION
    ),
    "Single deep-agent budget": (
        FLASH_EXTRACTION
        + token_cost(GEMINI_FLASH, input_tokens=4_800, output_tokens=1_600)
    ),
}


def main() -> None:
    for name, cost in PATHS.items():
        if name == "Opus direct baseline":
            print(f"{name}: ${cost:.6f}")
            continue
        savings = 1 - cost / OPUS_BASELINE
        print(f"{name}: ${cost:.6f} ({savings:.2%} cheaper than Opus)")


if __name__ == "__main__":
    main()
