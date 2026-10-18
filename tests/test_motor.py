import math

import numpy as np
import pytest

from denge import model, motor
from denge import simulasyon as sim


def test_rpm():
    r = 0.04
    assert motor.rpm(2 * math.pi * r, r) == pytest.approx(60.0)  # saniyede bir tur


def test_trapez_profil_mesafeyi_saglar():
    v, a = motor.trapez_profil(1.0, 4.0, 0.25)
    t_a = v / a
    assert v * (4.0 - t_a) == pytest.approx(1.0) and t_a == pytest.approx(1.0)


def test_el_hesabi_formulu(p):
    th0 = math.radians(10)
    el = motor.toparlanma_torku_el(p, th0, 0.5)
    assert el["statik"] == pytest.approx(p.m_b * p.g * p.l * math.sin(th0))
    assert el["dinamik"] == pytest.approx((p.I_yy + p.m_b * p.l**2) * 4 * th0 / 0.25)
    assert el["toplam"] == pytest.approx(el["statik"] + el["dinamik"])


def test_tutma_torku_dogrusal_olmayan_modelde_ivmeyi_sifirlar(p):
    th0 = math.radians(10)
    tau = motor.tutma_torku_tam(p, th0)
    turev = model.dinamik(p, [0, 0, th0, 0, 0, 0], tau / 2, tau / 2)
    assert abs(turev[3]) < 1e-10  # θ̈ = 0
    assert tau < p.m_b * p.g * p.l * math.sin(th0)  # el hesabının statik teriminden küçük


def test_tork_siralamasi(p):
    """tutma (tam) ≤ referans manevra tepe torku ≤ el hesabı."""
    th0 = math.radians(10)
    ref = sim.referans_toparlanma(p, th0, 2.0)
    tepe = np.max(np.abs(ref["dogrusal_olmayan"]["u"]))
    assert motor.tutma_torku_tam(p, th0) <= tepe <= motor.toparlanma_torku_el(p, th0, 0.5)["toplam"]


def test_uzun_manevrada_tepe_tork_tutma_torkuna_yaklasir(p):
    th0 = math.radians(10)
    tar = sim.toparlanma_taramasi(p, th0, [1.0, 2.0, 4.0, 8.0])
    assert np.all(np.diff(tar["u_dogrusal"]) < 0)
    assert tar["u_dogrusal"][-1] == pytest.approx(motor.tutma_torku_tam(p, th0), rel=0.05)


def test_min_durma_torku():
    noktalar = [(100.0, 0.3), (150.0, 0.05)]
    n0 = np.array([90.0, 160.0, 200.0, 400.0])
    ts = motor.min_durma_torku(n0, noktalar)
    assert np.isinf(ts[0])
    assert ts[2] == pytest.approx(max(0.3 / (1 - 100 / 200), 0.05 / (1 - 150 / 200)))
    assert np.all(np.diff(ts[1:]) < 0)
    # Sınırdaki motorun doğrusal eğrisi en az bir noktaya teğet, hiçbirinin altında değil
    for n0_i, ts_i in zip(n0[1:], ts[1:]):
        bosluk = [ts_i * (1 - n / n0_i) - t for n, t in noktalar]
        assert min(bosluk) == pytest.approx(0.0, abs=1e-12)


def test_motor_adayi_degerlendirme(tasarim):
    gerek = motor.gereksinimleri_hesapla(tasarim)
    V = tasarim.batarya_gerilimleri()
    # Test için yapay adaylar (gerçek ürün değil)
    guclu = motor.MotorAdayi("güçlü", 12.0, 400.0, 1.5, 4.0, 0.2, 30, 11)
    zayif = motor.MotorAdayi("zayıf", 12.0, 100.0, 0.1, 1.0, 0.1, 30, 3)
    s_guclu = {s["olcut"]: s["sonuc"] for s in motor.degerlendir(guclu, gerek, V)}
    s_zayif = {s["olcut"]: s["sonuc"] for s in motor.degerlendir(zayif, gerek, V)}
    assert all(v for k, v in s_guclu.items() if v is not None)
    # Zayıf motor tork, devir ve enkoder ölçütlerinin hepsinde kalır (gerilim ve sigorta satırları güvenlik kontrolüdür)
    assert not any(v for k, v in s_zayif.items() if v is not None and "gerilim" not in k and "akım" not in k)


def test_veri_sayfasindan_motor_modeli():
    a = motor.MotorAdayi("x", 12.0, 300.0, 0.8, 3.0, 0.2)
    m = a.motor_modeli()
    w0 = 300 * 2 * math.pi / 60
    assert m.K_t * (a.durma_akimi - a.bosta_akim) == pytest.approx(0.8)  # durma torku geri bulunur
    assert a.bosta_akim * m.R + m.K_e * w0 == pytest.approx(12.0)  # boşta gerilim dengesi


def test_enkoder_gereksinimi():
    e = motor.enkoder_gereksinimi(r=0.04, d=0.2, dv_hedef=0.02, pencere=0.01, n_max=120)
    assert e["cpr_min"] == pytest.approx(2 * math.pi * 0.04 / 0.0002)
    satir = motor.enkoder_tablosu(0.04, 0.2, 0.01, 120, [11], [30])[0]
    assert satir["cpr_teker"] == 4 * 11 * 30
    assert satir["dv"] == pytest.approx(2 * math.pi * 0.04 / 1320 / 0.01)


def test_rotor_ataleti_esigi_cekis_sinirina_denk_gelir(tasarim):
    """A' noktası: eşikteki J_m'de referans manevranın SF'li tepe torku çekiş sınırına eşit olmalı."""
    gerek = motor.gereksinimleri_hesapla(tasarim)
    p, SF, T = gerek["p"], gerek["SF"], gerek["T_ref"]
    J = gerek["J_m_esik"]
    assert 0 < J < tasarim.kayit("motor.rotor_ataleti_yansimis")["aralik"][1]
    tepe = motor.tepe_tork(p.degistir(J_m=J), math.radians(10), T)
    assert SF * tepe == pytest.approx(gerek["cekis_toplam"], rel=1e-4)
    assert gerek["nokta_A_asgari"][1] == pytest.approx(gerek["cekis_toplam"] / 2)
    # J_m arttıkça tutma torku ve referans tepe torku artar
    tablo = gerek["J_m_tablosu"]
    assert all(np.diff([x["tutma"] for x in tablo]) > 0) and all(np.diff([x["tepe_ref"] for x in tablo]) > 0)


def test_aday_motorun_yansiyan_rotor_ataleti():
    a = motor.MotorAdayi("x", 12.0, 300.0, 0.8, 3.0, 0.2, reduksiyon=30, ppr=11, rotor_ataleti=8e-7)
    assert a.J_m == pytest.approx(8e-7 * 900)


def test_dosyadaki_aday_ve_veri_sayfasi_tutarliligi(tasarim):
    a = motor.aday_tasarimdan(tasarim)
    assert a.bosta_devir == 530 and a.ppr == 11 and a.reduksiyon == pytest.approx(18.8)
    assert a.durma_torku == pytest.approx(2.6 * motor.KGFCM, rel=1e-3)
    assert 4 * a.ppr * a.reduksiyon == pytest.approx(827.2)  # sitedeki "800–850 sayım" notu


def test_aday_katsayisiz_gecer_katsayili_kalir(tasarim):
    """Rapordaki Mete önerisinin dayanağı: boş bataryada 530 RPM adayı A₀'ı geçer, A'yı (SF) geçemez."""
    g = motor.gereksinimleri_hesapla(tasarim)
    V = tasarim.batarya_gerilimleri()
    sonuc = {s["olcut"].split(":")[0]: s["sonuc"] for s in motor.degerlendir(motor.aday_tasarimdan(tasarim), g, V)}
    assert sonuc["A₀"] and not sonuc["A"] and sonuc["B"]
    assert 1.0 < motor.gereken_sf(motor.aday_tasarimdan(tasarim), g, V["min"]) < g["SF"]


def test_oran_taramasi_fiziksel_olarak_tutarli(tasarim):
    g = motor.gereksinimleri_hesapla(tasarim)
    seri = motor.seri_adaylari(tasarim)
    tarama = motor.oran_taramasi(seri, g, tasarim.batarya_gerilimleri()["min"])
    n0 = [x["n0"] for x in tarama]
    ts = [x["ts"] for x in tarama]
    assert all(np.diff(n0) < 0) and all(np.diff(ts) > 0)  # oran büyüdükçe devir düşer, tork artar
    # Çok yüksek oran B (seyir) noktasını, çok düşük oran A₀'ı karşılayamaz
    assert not tarama[-1]["nokta_B"][1] and not tarama[0]["nokta_A0"][1]
    # Sürekli model: nominal gerilimde uygun aralık 530 RPM'den yüksek oranlara uzanır
    ara = motor.oran_araligi(seri, g, tasarim.batarya_gerilimleri()["nominal"])
    assert ara["aralik"] is not None and ara["aralik"][0] < 30 < ara["aralik"][1]
