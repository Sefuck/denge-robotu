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


def test_fiziksel_parametrelerin_hepsi_tahmini(tasarim):
    """Parça alınmadı: robotun hiçbir fiziksel parametresi ölçülmüş olamaz."""
    fiziksel = [(y, k) for y, k in tasarim.kayitlar() if fiziksel_mi(y)]
    assert len(fiziksel) >= 25
    assert all(k["durum"] == "tahmini" for _, k in fiziksel)


@pytest.mark.parametrize(
    "bozma",
    [
        lambda v: v["teker"]["yaricap"].pop("kaynak"),
        lambda v: v["teker"]["yaricap"].update(durum="uydurma"),
        lambda v: v["teker"]["yaricap"].update(deger=0.5),  # aralık dışı
        lambda v: v["teker"]["kutle"].update(durum="öneri"),  # fiziksel parametre öneri olamaz
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


def test_batarya_gerilimi_24V_kisitina_uygun(tasarim):
    v = tasarim.batarya_gerilimleri()
    assert v["max"] <= tasarim.d("sartname.max_gerilim")
    # 6S Li-ion tam doluyken 25,2 V: şartnamedeki 24 V sınırını aşar (dokümanda uyarı)
    assert tasarim.degistir({"batarya.seri_hucre": 6}).batarya_gerilimleri()["max"] > 24.0
