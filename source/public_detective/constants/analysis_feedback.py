"""Centralizes all user-facing messages in pt-br for the analysis service."""


class ExclusionReason:
    """Provides standardized messages for why a file was excluded from analysis."""

    UNSUPPORTED_EXTENSION: str = "Extensão de arquivo não suportada."
    TOKEN_LIMIT_EXCEEDED: str = "Arquivo excluído porque o limite de {max_tokens} tokens foi excedido."
    CONVERSION_FAILED: str = "Falha ao converter o arquivo."
    TOTAL_SIZE_LIMIT_EXCEEDED: str = (
        "Arquivo excluído porque o tamanho total dos arquivos excedeu o limite de {max_size_mb:.1f} MB."
    )


class PrioritizationLogic:
    """Provides standardized messages for why a file was prioritized."""

    BY_METADATA: str = "Priorizado por conter o termo '{keyword}' nos metadados."
    BY_KEYWORD: str = "Priorizado por conter o termo '{keyword}' no nome."
    NO_PRIORITY: str = "Sem priorização."


class Warnings:
    """Provides standardized warning messages for the AI prompt."""

    TOKEN_LIMIT_EXCEEDED: str = (
        "O limite de {max_tokens} tokens foi excedido. Os seguintes arquivos foram ignorados: {ignored_files}"
    )
    TOTAL_SIZE_LIMIT_EXCEEDED: str = "Limite de {max_size_mb:.1f} MB excedido. Ignorados: {ignored_files}"
