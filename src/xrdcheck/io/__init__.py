"""파일 읽기 (XRDML · Rigaku RASX · X'Pert CSV · 2열 텍스트 · RTF 메타)."""

from xrdcheck.io.base import SUPPORTED_SUFFIXES, UnsupportedFileError, load_pattern

__all__ = ["SUPPORTED_SUFFIXES", "UnsupportedFileError", "load_pattern"]
