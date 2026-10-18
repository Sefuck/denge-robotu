import copy

import numpy as np
import pytest

from denge.kutle_merkezi import Bilesen, govde_ozellikleri
from denge.parametreler import Tasarim, fiziksel_mi


def test_her_parametrede_birim_durum_kaynak_var(tasarim):
    kayitlar = tasarim.kayitlar()
    assert len(kayitlar) > 40
    for yol, k in kayitlar:
        assert k["birim"] and k["durum"] and k["kaynak"].strip(), yol


def test_fiziksel_parametrelerin_hicbiri_olculmus_degil(tasarim):
    """Parça alınmadı: değerler site listesinden, satıcı referansından ya da tahminden gelir."""
    fiziksel = [(y, k) for y, k in tasarim.kayitlar() if fiziksel_mi(y)]
    assert len(fiziksel) >= 25
    assert all(k["durum"] in ("tahmini", "site", "doğrulanamadı") for _, k in fiziksel)
    durumlar = [k["durum"] for _, k in fiziksel]
    assert durumlar.count("site") >= 5 and durumlar.count("doğrulanamadı") >= 5


def test_site_ve_referans_kaynaklari_etiketli(tasarim):
    for yol, k in tasarim.kayitlar():
        if k["durum"] == "site":
            assert "site" in k["kaynak"].lower(), yol
        if k["durum"] == "doğrulanamadı":
            assert "[doğrulanamadı]" in k["kaynak"], yol
    # Motor veri sayfası değerleri sitede yok: rcdrone referansı, doğrulanamadı
    for alan in ("reduksiyon", "durma_torku", "durma_akimi", "bosta_akim"):
        k = tasarim.kayit(f"motor_adayi.{alan}")
        assert k["durum"] == "doğrulanamadı" and "rcdrone" in k["kaynak"]


@pytest.mark.parametrize(
    "bozma",
    [
        lambda v: v["teker"]["yaricap"].pop("kaynak"),
        lambda v: v["teker"]["yaricap"].update(durum="uydurma"),
        lambda v: v["teker"]["yaricap"].update(deger=0.5),  # aralık dışı
        lambda v: v["teker"]["kutle"].update(durum="öneri"),  # fiziksel parametre öneri olamaz
        lambda v: v["motor_adayi"]["durma_torku"].update(kaynak="rcdrone"),  # [doğrulanamadı] etiketi yok
    ],
)
def test_hatali_parametre_dosyasi_reddedilir(tasarim, bozma):
    veri = copy.deepcopy(tasarim.veri)
    bozma(veri)
    with pytest.raises(ValueError):
        Tasarim(veri)


def test_kutle_butcesi(tasarim):
    kutusuz = tasarim.bilesenler(kutulu=False)
    kutulu = tasarim.bilesenler(kutulu=True)
    assert sum(b.ad.startswith("Motor") for b in kutusuz) == 2  # simetrik iki motor
    m_kutu = tasarim.d("yuk.kutu.kutle")
    assert sum(b.kutle for b in kutulu) - sum(b.kutle for b in kutusuz) == pytest.approx(m_kutu)
    assert tasarim.toplam_kutle(kutulu=True) == pytest.approx(sum(b.kutle for b in kutulu) + 2 * tasarim.d("teker.kutle"))


def test_paralel_eksen_teoremi():
    """İki eşit noktasal kütle ±a'da: KM ortada, atalet 2·m·a²."""
    m, a = 0.5, 0.1
    g = govde_ozellikleri([Bilesen("a", m, (0, 0, a), (0, 0, 0)), Bilesen("b", m, (0, 0, -a), (0, 0, 0))])
    assert np.allclose(g.km, 0)
    assert g.atalet[0, 0] == pytest.approx(2 * m * a**2)
    assert g.atalet[1, 1] == pytest.approx(2 * m * a**2)
    assert g.atalet[2, 2] == pytest.approx(0)


def test_kutu_kutusu_atalet_formulu():
    m, dx, dy, dz = 2.0, 0.1, 0.2, 0.3
    g = govde_ozellikleri([Bilesen("k", m, (0, 0, 0), (dx, dy, dz))])
    assert np.allclose(np.diag(g.atalet), m / 12 * np.array([dy**2 + dz**2, dx**2 + dz**2, dx**2 + dy**2]))


def test_site_bataryasi_3S_ve_24V_kisitina_uygun(tasarim):
    v = tasarim.batarya_gerilimleri()
    assert tasarim.d("batarya.seri_hucre") == 3
    assert v["min"] == pytest.approx(9.9) and v["nominal"] == pytest.approx(11.1) and v["max"] == pytest.approx(12.6)
    assert v["max"] <= tasarim.d("sartname.max_gerilim")
