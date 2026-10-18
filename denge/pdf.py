"""Markdown belgelerini PDF'e çevirir: pandoc (pypandoc_binary) → HTML + MathML → Chrome (başsız) ile yazdırma.

Formüller MathML olarak çizilir (JavaScript gerekmez), şekiller HTML'e gömülür.
Belgeler arası bağlantılar (.md) PDF'te karşı PDF dosyasına yönlendirilir.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

CHROME_ADAYLARI = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)


def chrome_yolu() -> str:
    for aday in (os.environ.get("CHROME"), *CHROME_ADAYLARI, shutil.which("google-chrome"), shutil.which("chromium")):
        if aday and Path(aday).exists():
            return aday
    raise FileNotFoundError("Chrome bulunamadı; CHROME ortam değişkeniyle yolunu verin.")


def pdf_uret(md: Path, pdf: Path, css: Path, baslik: str) -> int:
    """md → pdf. Dönen değer: PDF sayfa sayısı."""
    import pypandoc
    from pypdf import PdfReader

    pdf.parent.mkdir(parents=True, exist_ok=True)
    metin = md.read_text(encoding="utf-8")
    metin = re.sub(r"\(([\w.-]+)\.md(#[^)]*)?\)", r"(\1.pdf)", metin)  # belge bağlantıları → PDF dosyası
    # LaTeX'teki ondalık virgül {,} MathML'de "1, 370" gibi boşluklu çıkıyor; PDF için metin virgüle çevir
    metin = re.sub(r"(\d)\{,\}(\d)", r"\1\\text{,}\2", metin)
    with tempfile.TemporaryDirectory() as gecici:
        ara_md = Path(gecici) / md.name
        ara_md.write_text(metin, encoding="utf-8")
        html = Path(gecici) / (md.stem + ".html")
        pypandoc.convert_file(
            str(ara_md), "html5", format="markdown", outputfile=str(html),
            extra_args=["--standalone", "--embed-resources", "--mathml", f"--resource-path={md.parent}",
                        f"--css={css}", "--metadata", f"pagetitle={baslik}", "--metadata", "lang=tr"],
        )
        profil = Path(gecici) / "chrome-profil"  # kullanıcının açık Chrome'una dokunmamak için ayrı profil
        subprocess.run(
            [chrome_yolu(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={profil}",
             f"--print-to-pdf={pdf}", "--virtual-time-budget=5000", html.as_uri()],
            check=True, capture_output=True, timeout=180,
        )
    return len(PdfReader(str(pdf)).pages)
