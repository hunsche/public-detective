"""Centralizes all user-facing messages in pt-br for the analysis service."""


class ExclusionReason:
    """Provides standardized messages for why a file was excluded from analysis."""

    UNSUPPORTED_EXTENSION: str = "Extensão de arquivo não suportada."
    EXTRACTION_FAILED: str = "Falha ao extrair o arquivo compactado."
    TOKEN_LIMIT_EXCEEDED: str = "Arquivo excluído porque o limite de {max_tokens} tokens foi excedido."
    CONVERSION_FAILED: str = "Falha ao converter o arquivo."
    LOCK_FILE: str = "Arquivo de bloqueio temporário, ignorado pois não contém o documento real."
    PARTIAL_CONVERSION: str = (
        "A conversão do arquivo foi parcial. "
        "Alguns conteúdos (como gráficos ou abas sem dados) podem ter sido ignorados."
    )
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

    IGNORED_NON_DATA_SHEET: str = (
        "A planilha '{sheet_name}' foi ignorada por não conter dados tabulares (tipo: {sheet_type})."
    )
    TOKEN_LIMIT_EXCEEDED: str = (
        "O limite de {max_tokens} tokens foi excedido. Os seguintes arquivos foram ignorados: {ignored_files}"
    )
    TOTAL_SIZE_LIMIT_EXCEEDED: str = "Limite de {max_size_mb:.1f} MB excedido. Ignorados: {ignored_files}"
