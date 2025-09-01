"""Centralizes all user-facing messages in pt-br for the analysis service."""


class ExclusionReason:
    """Provides standardized messages for why a file was excluded from analysis."""

    UNSUPPORTED_EXTENSION = "Extensão de arquivo não suportada."
    FILE_LIMIT_EXCEEDED = (
        "Arquivo excluído porque o limite de {max_files} arquivos para análise foi excedido."
    )
    TOTAL_SIZE_LIMIT_EXCEEDED = (
        "Arquivo excluído porque o tamanho total dos arquivos excedeu o limite de {max_size_mb:.1f} MB."
    )


class PrioritizationLogic:
    """Provides standardized messages for why a file was prioritized."""

    BY_KEYWORD = "Priorizado por conter o termo '{keyword}' no nome."
    NO_PRIORITY = "Sem priorização."


class Warnings:
    """Provides standardized warning messages for the AI prompt."""

    FILE_LIMIT_EXCEEDED = (
        "Limite de {max_files} arquivos excedido. Ignorados: {ignored_files}"
    )
    TOTAL_SIZE_LIMIT_EXCEEDED = "Limite de {max_size_mb:.1f} MB excedido. Ignorados: {ignored_files}"
