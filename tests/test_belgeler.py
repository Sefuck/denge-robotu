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


def test_step_bolumu_istenen_basliklari_ve_etiketleri_tasir():
    tam = (SABLON / "hafta03.md").read_text(encoding="utf-8")
    bolum = tam.split("## 10. Step motor")[1].split("## Ek A")[0]
    assert "pull-out eğrisi bulunamadı" in bolum and "[doğrulanamadı]" in bolum
    for ic in ("### 10.5 Adım kaçırma", "### 10.9 Pasif", "### 10.10 Ölçüm planı", "### 10.11 Karşılaştırma"):
        assert ic in bolum
    uretilen = (KOK / "docs" / "hafta03_model_tork_km.md").read_text(encoding="utf-8")
    for baslik in ("Maliyet", "Tork payı", "Hız payı", "Konum çözünürlüğü", "Kütle", "Akım ve pil süresi", "Kontrol karmaşıklığı", "Riskler"):
        assert f"**{baslik}**" in uretilen
    assert "@@" not in uretilen


def test_ozet_satin_alinan_motor_kararini_ve_olcum_planini_anlatir():
    ozet = (SABLON / "hafta03_ozet.md").read_text(encoding="utf-8")
    assert "Satın alınan 1000 RPM motor: @@sa_karar_kucuk@@" in ozet and "@@bag_11_5@@" in ozet and "@@bag_11_6@@" in ozet
    assert "Step motor seçeneği" in ozet
    uretilen = (KOK / "docs" / "hafta03_toplanti_ozeti.md").read_text(encoding="utf-8")
    assert "Satın alınan 1000 RPM motor: sınırda" in uretilen


def test_satin_alinan_bolumu_karar_gerekce_cozum_olcum_tasir():
    tam = (SABLON / "hafta03.md").read_text(encoding="utf-8")
    bolum = tam.split("## 11. Satın alınan motor")[1].split("## Ek A")[0]
    for ic in ("### 11.2", "### 11.3 Karar", "### 11.4 Çözüm", "### 11.5 Ölçüm planı", "### 11.6 Öneri", "**a) Daha küçük teker.**",
               "**b) Motor ile teker arasına ek redüksiyon.**", "**c) Kütle ve KM yüksekliğini azaltmak.**", "[doğrulanamadı]"):
        assert ic in bolum


def test_simulasyon_bolumu_istenen_basliklari_ve_oneriyi_tasir():
    tam = (SABLON / "hafta03.md").read_text(encoding="utf-8")
    bolum = tam.split("## 12. Simülasyon")[1].split("## Ek A")[0]
    for ic in ("### 12.1", "### 12.2 Simülasyon çekirdeği", "### 12.3 Sensörler", "### 12.4 Durum kestirimi", "### 12.5 Kontrolcüler",
               "### 12.6 Senaryolar", "### 12.7 Sonuçlar", "### 12.8 Motor kararı", "### 12.9 Sınırlamalar", "### 12.10",
               "MuJoCo", "PyBullet", "[öneri]", "@@tablo_ik_matris@@", "@@tablo_ik_motorlar@@", "@@ik_kalanlar@@"):
        assert ic in bolum
    ozet = (SABLON / "hafta03_ozet.md").read_text(encoding="utf-8")
    assert "@@bag_12_8@@" in ozet and "simülasyon" in ozet.lower()
    uretilen = (KOK / "docs" / "hafta03_model_tork_km.md").read_text(encoding="utf-8")
    assert "## 12. Simülasyon" in uretilen and "@@" not in uretilen
    assert (KOK / "docs" / "simulasyon" / "sonuclar.csv").exists()


def test_3d_alt_bolumu_ve_video_baglantilari():
    tam = (SABLON / "hafta03.md").read_text(encoding="utf-8")
    bolum = tam.split("### 12.11 3D simülasyon")[1].split("## Ek A")[0]
    for ic in ("MuJoCo", "@@tablo_ik3@@", "**Farklar ve nedenleri.**", "mjpython", "[öneri]"):
        assert ic in bolum
    for hedef in re.findall(r"\]\((video/[^)]+\.mp4)\)", bolum):
        assert (KOK / "docs" / hedef).exists(), hedef
    ozet = (SABLON / "hafta03_ozet.md").read_text(encoding="utf-8")
    assert "@@bag_12_11@@" in ozet and "MuJoCo" in ozet
