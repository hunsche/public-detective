"""Configuration for the RankingService."""

from dataclasses import dataclass, field

from source.public_detective.models.file_records import ExclusionReason


@dataclass
class RankingConfig:
    """Configuration for the RankingService."""

    W_IMPACT: float = 1.5
    W_QUALITY: float = 1.0
    W_COST: float = 0.1
    W_VOTES: float = 0.2
    STABILITY_PERIOD_HOURS: int = 48
    HIGH_IMPACT_KEYWORDS: list[str] = field(
        default_factory=lambda: [
            "saúde",
            "hospitalar",
            "educação",
            "saneamento",
            "infraestrutura",
        ]
    )
    QUALITY_PENALTY_POINTS: dict[ExclusionReason, int] = field(
        default_factory=lambda: {
            ExclusionReason.EXTRACTION_FAILED: 20,
            ExclusionReason.CONVERSION_FAILED: 15,
            ExclusionReason.UNSUPPORTED_EXTENSION: 10,
            ExclusionReason.LOCK_FILE: 5,
            ExclusionReason.TOKEN_LIMIT_EXCEEDED: 5,
        }
    )
    IMPACT_VALUE_THRESHOLDS: dict[str, int] = field(
        default_factory=lambda: {
            "HIGH": 1_000_000,
            "MEDIUM": 100_000,
        }
    )
    IMPACT_VALUE_SCORES: dict[str, int] = field(
        default_factory=lambda: {
            "HIGH": 50,
            "MEDIUM": 25,
        }
    )
    IMPACT_KEYWORD_SCORE: int = 20
    TEMPORAL_SCORE_ENABLED: bool = True
    TEMPORAL_WINDOW_DAYS_MIN: int = 5
    TEMPORAL_WINDOW_DAYS_MAX: int = 15
    W_TEMPORAL: float = 0.3


ranking_config = RankingConfig()
