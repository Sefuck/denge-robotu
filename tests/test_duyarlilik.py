"""Parametre değişince sonuçlar fiziksel olarak beklenen yönde ve oranda değişiyor mu?"""

import math

import numpy as np
import pytest

from denge import yuva_analizi as ya
from denge import model, motor

KUTLE_YOLLARI = [
    "govde.motor.kutle", "govde.sasi.kutle", "govde.elektronik.kutle", "govde.batarya.kutle",
    "govde.acil_durdurma.kutle", "govde.ir_ve_sarj_kontaklari.kutle", "yuk.yuva.kutle", "yuk.kutu.kutle", "teker.kutle",
]


def test_butun_kutleler_iki_katina_cikinca(tasarim):
    """Boyut analizi: KM ve kutuplar değişmez, torklar iki katına çıkar."""
    iki_kat = tasarim.degistir({y: 2 * tasarim.d(y) for y in KUTLE_YOLLARI})
    p1, p2 = tasarim.model(), iki_kat.model()
    assert p2.l == pytest.approx(p1.l)
    assert model.kararsiz_kutup(p2) == pytest.approx(model.kararsiz_kutup(p1))
    th0 = math.radians(10)
    assert motor.toparlanma_torku_el(p2, th0, 0.5)["toplam"] == pytest.approx(2 * motor.toparlanma_torku_el(p1, th0, 0.5)["toplam"])
    assert motor.tutma_torku_tam(p2, th0) == pytest.approx(2 * motor.tutma_torku_tam(p1, th0))


def test_yercekimi_dort_katina_cikinca_kutup_iki_katina(p):
    assert model.kararsiz_kutup(p.degistir(g=4 * p.g)) == pytest.approx(2 * model.kararsiz_kutup(p))


def test_sabit_pivot_ve_noktasal_kutle_sinirinda_kok_g_bolu_l(p):
    """Teker ataleti çok büyük (aks sabit) → p = √(m g l / J_O); ayrıca I_yy → 0 → p = √(g/l)."""
    sabit = p.degistir(J_w=1e6)
    assert model.kararsiz_kutup(sabit) == pytest.approx(math.sqrt(p.m_b * p.g * p.l / (p.I_yy + p.m_b * p.l**2)), rel=1e-4)
    nokta = sabit.degistir(I_yy=0.0)
    assert model.kararsiz_kutup(nokta) == pytest.approx(math.sqrt(p.g / p.l), rel=1e-4)


def test_batarya_yukselince_km_ve_statik_tork_artar(tasarim):
    tar = ya.batarya_taramasi(tasarim, np.linspace(0.03, 0.23, 6))
    assert np.all(np.diff(tar["l"]) > 0)
    assert np.all(np.diff(tar["tau_statik"]) > 0)
    assert np.all(np.diff(tar["kok_g_l"]) < 0)


def test_teker_buyuyunce_devir_azalir_enkoder_ihtiyaci_artar(tasarim):
    buyuk = tasarim.degistir({"teker.yaricap": 0.05})
    r1, r2 = tasarim.d("teker.yaricap"), 0.05
    h1 = motor.hareket_tablosu(tasarim, tasarim.model())
    h2 = motor.hareket_tablosu(buyuk, buyuk.model())
    for a, b in zip(h1, h2):
        assert b["rpm"] == pytest.approx(a["rpm"] * r1 / r2)
    e1 = motor.enkoder_gereksinimi(r1, 0.2, 0.02, 0.01, 100)["cpr_min"]
    e2 = motor.enkoder_gereksinimi(r2, 0.2, 0.02, 0.01, 100)["cpr_min"]
    assert e2 == pytest.approx(e1 * r2 / r1)


def test_hareket_suresi_kisalinca_devir_ters_orantili_artar(tasarim):
    hizli = tasarim.degistir({"hedef.o1_sure": 2.0})
    a = motor.hareket_tablosu(tasarim, tasarim.model())[0]
    b = motor.hareket_tablosu(hizli, hizli.model())[0]
    assert b["rpm"] == pytest.approx(2 * a["rpm"])


def test_el_hesabi_dinamik_payi_ters_kare_ile_artar(p):
    th0 = math.radians(10)
    assert motor.toparlanma_torku_el(p, th0, 0.25)["dinamik"] == pytest.approx(4 * motor.toparlanma_torku_el(p, th0, 0.5)["dinamik"])


def test_emniyet_katsayisi_tork_gereksinimini_dogrusal_olcekler(tasarim):
    g1 = motor.gereksinimleri_hesapla(tasarim)
    g2 = motor.gereksinimleri_hesapla(tasarim.degistir({"hedef.emniyet_katsayisi": 3.0}))
    assert g2["nokta_A"][1] == pytest.approx(g1["nokta_A"][1] * 3.0 / tasarim.d("hedef.emniyet_katsayisi"))


@pytest.mark.parametrize("ad, deger", [("J_m", 1e-3), ("b", 0.02)])
def test_rotor_ataleti_ve_sonum_kararsiz_kutbu_yavaslatir(p, ad, deger):
    p_ = p.degistir(**{ad: deger})
    assert 0 < model.kararsiz_kutup(p_) < model.kararsiz_kutup(p)


def test_kutu_agirlasinca_km_degisimi_artar(tasarim):
    farklar = []
    for m in (0.02, 0.05, 0.10, 0.15):
        t = tasarim.degistir({"yuk.kutu.kutle": m})
        farklar.append(t.model(kutulu=True).l - t.model(kutulu=False).l)
    assert np.all(np.diff(farklar) > 0) and farklar[0] > 0  # üst yuva KM'yi yükseltir


def test_kutu_kaymasi_trim_acisini_dogrusal_degistirir(tasarim):
    s = ya.kayma_etkisi(tasarim, [0.001, 0.002, 0.004], f_x_max=1.0)
    dtrim = np.array([x["dtrim"] for x in s])
    assert np.all(dtrim < 0)  # kutu öne kayınca gövde geriye trimlenir
    assert dtrim[1] == pytest.approx(2 * dtrim[0], rel=1e-3) and dtrim[2] == pytest.approx(4 * dtrim[0], rel=1e-3)
