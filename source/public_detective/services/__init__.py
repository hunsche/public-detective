"""This module initializes the services package.

It also re-exports key models and services to provide a simpler, flatter
import structure for other parts of the application. This helps to decouple
the application's internal structure from its public interface.
"""

from public_detective.models.candidates import AIFileCandidate
from public_detective.services.analysis import AnalysisService
from public_detective.services.converter import ConverterService
from public_detective.services.pricing import PricingService
from public_detective.services.ranking import RankingService

__all__ = [
    "AnalysisService",
    "ConverterService",
    "PricingService",
    "RankingService",
    "AIFileCandidate",
]
