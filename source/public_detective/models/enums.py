"""This module defines the enumerations for the application."""

from enum import StrEnum


class ExclusionReason(StrEnum):
    """Provides standardized messages for why a file was excluded from analysis."""

    UNSUPPORTED_EXTENSION = "Extensão de arquivo não suportada."
    EXTRACTION_FAILED = "Falha ao extrair o arquivo compactado. O arquivo pode estar corrompido ou protegido por senha."
    TOKEN_LIMIT_EXCEEDED = "Arquivo excluído porque o limite de {max_tokens} tokens foi excedido."
    CONVERSION_FAILED = "Falha ao converter o arquivo."
    LOCK_FILE = "Arquivo de bloqueio temporário, ignorado pois não contém o documento real."
    PARTIAL_CONVERSION = (
        "A conversão do arquivo foi parcial. "
        "Alguns conteúdos (como gráficos ou abas sem dados) podem ter sido ignorados."
    )
    TOTAL_SIZE_LIMIT_EXCEEDED = (
        "Arquivo excluído porque o tamanho total dos arquivos excedeu o limite de {max_size_mb:.1f} MB."
    )

    def __str__(self) -> str:
        """Returns the string representation of the enum member."""
        return self.value

    def format(self, **kwargs) -> str:
        """Formats the string with the given arguments."""
        return self.value.format(**kwargs)


class PrioritizationLogic(StrEnum):
    """Provides standardized messages for why a file was prioritized."""

    BY_METADATA = "Priorizado por conter o termo '{keyword}' nos metadados."
    BY_KEYWORD = "Priorizado por conter o termo '{keyword}' no nome."
    NO_PRIORITY = "Sem priorização."

    def __str__(self) -> str:
        """Returns the string representation of the enum member."""
        return self.value

    def format(self, **kwargs) -> str:
        """Formats the string with the given arguments."""
        return self.value.format(**kwargs)


class Warnings(StrEnum):
    """Provides standardized warning messages for the AI prompt."""

    IGNORED_NON_DATA_SHEET = "A planilha '{sheet_name}' foi ignorada por não conter dados tabulares (tipo: {sheet_type})."
    TOKEN_LIMIT_EXCEEDED = "O limite de {max_tokens} tokens foi excedido. Os seguintes arquivos foram ignorados: {ignored_files}"
    TOTAL_SIZE_LIMIT_EXCEEDED = "Limite de {max_size_mb:.1f} MB excedido. Ignorados: {ignored_files}"
    IGNORED_FILES_BY_REASON = "Arquivos ignorados por '{reason}': {files_str}"

    def __str__(self) -> str:
        """Returns the string representation of the enum member."""
        return self.value

    def format(self, **kwargs) -> str:
        """Formats the string with the given arguments."""
        return self.value.format(**kwargs)
