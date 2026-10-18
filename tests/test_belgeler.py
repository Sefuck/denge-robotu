"""Belge ifadeleri: özet sade ve formülsüz; kaynak adresi gizlenmez; özet bağlantıları tam belgede karşılık bulur."""

import re
from pathlib import Path

import pytest

from denge.rapor import bolum_baglari, github_slug

KOK = Path(__file__).resolve().parent.parent
SABLON = KOK / "docs" / "sablon"
YASAK = ("başka bir grub", "başka bir grup", "gruba ait", "bağlayıcı değil", "bağlayıcı değildir")


@pytest.mark.parametrize("dosya", ["parametreler.toml", "README.md", "docs/sablon/hafta03.md", "docs/sablon/hafta03_ozet.md"])
def test_eski_kaynak_ifadeleri_yok(dosya):
    metin = (KOK / dosya).read_text(encoding="utf-8").lower()
    assert not [y for y in YASAK if y in metin]


def test_kaynak_adresi_parametre_dosyasinda_ve_kaynakcada_duruyor():
    assert "cdtp-robot.netlify.app" in (KOK / "parametreler.toml").read_text(encoding="utf-8")
    tam = (SABLON / "hafta03.md").read_text(encoding="utf-8")
    assert "cdtp-robot.netlify.app" in tam.split("## Kaynaklar")[1]


def test_ozet_sade_formulsuz_ve_liste_adini_anmiyor():
    ozet = (SABLON / "hafta03_ozet.md").read_text(encoding="utf-8")
    assert "netlify" not in ozet.lower()
    assert "$" not in ozet and "\\" not in ozet  # LaTeX yok
    assert "ön malzeme listesi" in ozet.lower() and "Mete'nin seçimiyle kesinleşecek" in ozet
    for bolum in ("Danışmanın istediği", "Ne yaptık", "Ana sonuçlar", "Öneriler ve kararlar", "Bekleyenler", "Sonraki hafta", "Haftalık rubrik"):
        assert f"## {bolum}" in ozet


def test_ozet_bagları_tam_belgedeki_basliklara_karsilik_gelir():
    ozet = (SABLON / "hafta03_ozet.md").read_text(encoding="utf-8")
    tam = (SABLON / "hafta03.md").read_text(encoding="utf-8")
    baglar = bolum_baglari(tam, "x.md")
    kullanilan = set(re.findall(r"@@(bag_\w+)@@", ozet))
    assert kullanilan and kullanilan <= set(baglar)


def test_github_slug():
    assert github_slug("4.7 Aday motor: JGB37-520 12 V 530 RPM, Hall enkoderli (Mete'ye öneri)") == \
        "47-aday-motor-jgb37-520-12-v-530-rpm-hall-enkoderli-meteye-öneri"
    assert github_slug("3.6 Transfer fonksiyonları ve açık çevrim kutuplar") == "36-transfer-fonksiyonları-ve-açık-çevrim-kutuplar"


def test_uretilmis_ozette_yer_tutucu_ve_liste_adi_yok():
    ozet = (KOK / "docs" / "hafta03_toplanti_ozeti.md").read_text(encoding="utf-8")
    assert "@@" not in ozet and "netlify" not in ozet.lower()
