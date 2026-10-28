"""PyInstaller --version-file용 Windows 버전 정보(파일 속성 > 자세히: 제품 이름·버전·개발자)를 만든다."""

import sys
from pathlib import Path

from xrdcheck import __author__, __version__

TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={v4}, prodvers={v4}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041204B0', [
      StringStruct('CompanyName', '{author}'),
      StringStruct('FileDescription', 'XRD 비정질 판정 도우미'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'XRD_Checker'),
      StringStruct('LegalCopyright', '개발자: {author}'),
      StringStruct('OriginalFilename', 'XRD_Checker.exe'),
      StringStruct('ProductName', 'XRD 비정질 판정 도우미'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [0x0412, 1200])])
  ]
)
"""

if __name__ == "__main__":
    nums = [int(n) for n in __version__.split(".")] + [0, 0, 0, 0]
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(TEMPLATE.format(v4=tuple(nums[:4]), ver=__version__, author=__author__), encoding="utf-8")
