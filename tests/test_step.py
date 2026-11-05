"""Step motor seçeneği: DC analizi değişmedi; ivme girişli model; geçici eğri; adım kaçırma; pratik hesaplar."""

import copy
import math

import numpy as np
import pint
import pytest

from denge import model, motor, step
from denge import simulasyon as sim
from denge.kutle_merkezi import yere_degme_acilari
from denge.parametreler import Tasarim, step_parametresi_mi

ureg = pint.UnitRegistry()


@pytest.fixture(scope="module")
def st(tasarim):
    return tasarim.tahrik_tasarimi("step")


@pytest.fixture(scope="module")
def ps(st):
    return st.model(kutulu=True)


@pytest.fixture(scope="module")
def egri(tasarim):
    return step.PullOut(tasarim)


# -- Motor tipi parametresi: DC sonuçları sürüm 0.2 ile aynı ---------------------------------------
def test_dc_sayilari_surum_02_ile_ayni(tasarim):
    """Sürüm 0.2'de belgeye giren değerler (3. hafta toplantısı): motor tipi eklenince değişmemeli."""
    dc = tasarim.tahrik_tasarimi("dc")
    p = dc.model(kutulu=True)
    g = motor.gereksinimleri_hesapla(dc)
    assert dc.toplam_kutle(kutulu=True) == pytest.approx(1.31)
    assert model.kararsiz_kutup(p) == pytest.approx(11.41, abs=0.005)
    assert model.kilitli_kutup(p) == pytest.approx(6.62, abs=0.005)
    assert p.J_m == 0.0 and p.l == pytest.approx(0.0783, abs=5e-5)
    assert g["nokta_A"][1] == pytest.approx(0.196, abs=5e-4) and g["nokta_A"][0] == pytest.approx(111.4, abs=0.1)
    assert g["cekis_toplam"] == pytest.approx(0.292, abs=5e-4)
    seri = motor.seri_adaylari(dc)
    aday = motor.aday_tasarimdan(dc)
    V = dc.batarya_gerilimleri()["min"]
    assert motor.gereken_sf(aday, g, V) == pytest.approx(1.60, abs=0.005)
    assert motor.gereken_sf(next(a for a in seri if a.reduksiyon == 30), g, V) == pytest.approx(1.96, abs=0.005)


def test_motor_tipi_gecersizse_reddedilir(tasarim):
    veri = copy.deepcopy(tasarim.veri)
    veri["tahrik"]["tip"]["deger"] = "hidrolik"
    with pytest.raises(ValueError):
        Tasarim(veri)


def test_motor_kutlesi_parametre_dosyasindan_toplam_kutleye_gecer(tasarim, st):
    m_dc, m_st = tasarim.d("govde.motor.kutle"), st.d(f"{st.step_sargisi()}.kutle")
    assert m_dc == pytest.approx(0.15) and m_st == pytest.approx(0.30)
    assert st.toplam_kutle() - tasarim.tahrik_tasarimi("dc").toplam_kutle() == pytest.approx(2 * (m_st - m_dc))


def test_aksa_eklenen_kutle_mbl_carpimini_degistirmez_km_alcalir(tasarim, st):
    """Motorlar aks üstünde (z = 0): m_b l aynı kalır, statik tork değişmez, l küçülür."""
    d, s = tasarim.tahrik_tasarimi("dc").model(), st.model()
    assert s.m_b * s.l == pytest.approx(d.m_b * d.l, rel=1e-9) and s.l < d.l
    assert s.J_m == pytest.approx(st.d(f"{st.step_sargisi()}.rotor_ataleti"))


def test_step_parametreleri_etiketli(tasarim):
    kayit = [(y, k) for y, k in tasarim.kayitlar() if step_parametresi_mi(y)]
    assert len(kayit) > 30
    assert all(k["durum"] in ("tahmini", "ön liste", "doğrulanamadı", "ölçülmüş") for _, k in kayit)
    # Kardeş motor eğrileri bu motorun eğrisi diye geçemez
    for ad in ("hs15_1504s", "hs15_1684s"):
        assert "kardeş motor" in tasarim.kayit(f"step_egri.{ad}.devir")["kaynak"]


# -- İvme girişli model --------------------------------------------------------------------------
def test_ivme_girisli_kutup_tork_modelinin_sifiri(ps):
    tf = model.transfer_fonksiyonu_analitik(ps)
    A, B, C, D = model.ivme_girisli_durum_uzay(ps)
    ozd = np.sort(np.linalg.eigvals(A).real)
    assert ozd == pytest.approx([-math.sqrt(tf["z2"]), 0, 0, math.sqrt(tf["z2"])], abs=1e-6)
    assert max(ozd) > 0  # sağ yarı düzlemde kutup: açık çevrim kararsız
    assert model.kontrol_edilebilirlik_rangi(A, B) == 4
    assert C.shape == (4, 4) and D.shape == (4, 1)


def test_bagil_ivme_girisli_kutup_kilitli_teker_kutbu(ps):
    A, *_ = model.bagil_ivme_girisli_durum_uzay(ps)
    assert np.max(np.linalg.eigvals(A).real) == pytest.approx(model.kilitli_kutup(ps), rel=1e-6)


def test_ivme_girisli_model_bilinmeyen_motora_bagli_degil(ps):
    """J_m ve b iç kuvvettir: hareketi değil, yalnız motordan istenen torku değiştirir."""
    A0, B0, *_ = model.ivme_girisli_durum_uzay(ps)
    A1, B1, *_ = model.ivme_girisli_durum_uzay(ps.degistir(J_m=2e-3, b=0.02))
    assert np.allclose(A0, A1) and np.allclose(B0, B1)
    u0 = model.ivmeden_tork(ps, 0.0, 0.0, 0.0, 1.0, 0.0)
    assert model.ivmeden_tork(ps.degistir(J_m=2e-3), 0.0, 0.0, 0.0, 1.0, 0.0) > u0


def test_ivme_girisli_dinamik_tam_modelle_tutarli(ps):
    """a'dan hesaplanan tork tam modele verilince aynı ẍ ve θ̈ çıkar (J_m, b dahil)."""
    p = ps.degistir(J_m=5e-4, b=0.01)
    for a, th, thd, xd in ((1.0, 0.2, -0.3, 0.1), (-2.0, -0.15, 0.8, -0.2), (0.0, 0.1, 0.0, 0.0)):
        _, _, _, thdd = model.ivme_girisli_dinamik(p, [0.0, xd, th, thd], a)
        u = model.ivmeden_tork(p, th, thd, thdd, a, xd)
        _, vd, _, thdd2, _, _ = model.dinamik(p, [0.0, xd, th, thd, 0.0, 0.0], u / 2, u / 2)
        assert vd == pytest.approx(a, abs=1e-9) and thdd2 == pytest.approx(thdd, abs=1e-9)


def test_ivme_girisli_dogrusal_model_kucuk_acida_ortusur(ps):
    A, B, *_ = model.ivme_girisli_durum_uzay(ps)
    durum = np.array([0.0, 0.0, math.radians(0.5), 0.0])
    a = 0.1
    assert np.allclose((A @ durum + B[:, 0] * a), model.ivme_girisli_dinamik(ps, durum, a), atol=1e-5)


def test_toparlanma_ivme_girisiyle_ayni_yorungeyi_izler(ps):
    """Polinomdan a(t) uygulanınca θ(t) referansı izler; tork ters dinamikle aynıdır."""
    th0 = math.radians(10)
    y = sim.referans_toparlanma(ps, th0, 2.0)
    st_y = sim.ivme_girisli_yorunge(ps, y)
    nl = y["dogrusal_olmayan"]
    assert np.allclose(st_y["xd"], nl["xd"], atol=2e-5)
    assert np.allclose(st_y["u"], nl["u"], atol=1e-5)
    ileri = sim.ivme_girisli_ileri_simulasyon(ps, sim.ivme_fonksiyonu(ps, y), [0.0, 0.0, th0, 0.0], y["t"])
    assert np.max(np.abs(ileri["theta"] - y["theta"])) < math.radians(0.2)
    assert abs(ileri["theta"][-1]) < math.radians(0.2)


# -- Geçici eğri ---------------------------------------------------------------------------------
def test_kardes_egrileri_kurala_uyar(egri):
    """Kural sınaması: 1504S'in biçimi 1684S'ten öngörülür. Gerilim ölçeği ise ölçümle doğrulanacak."""
    assert egri.capraz_hata() < 0.10
    for k in egri.kardesler:
        assert 0.8 < k.plato / k.T_tutma < 1.1  # test akımı etkin: tepe olsaydı oran ≈ 0,71 olurdu


def test_kardes_akimi_tepe_sayilsaydi_tork_tutmazdi(egri):
    for k in egri.kardesler:
        assert k.plato > 1.15 * k.T_tutma / math.sqrt(2)


@pytest.mark.parametrize("V, I", [(12.0, 1.5), (9.9, 1.5), (11.1, 2.1)])
def test_egri_sinirlari_tutarli(egri, V, I):
    n = np.linspace(0, 600, 121)
    alt, ust = egri.alt(n, V, I), egri.ust(n, V, I)
    assert np.all(alt <= ust + 1e-12)
    assert np.all(np.diff(alt) <= 1e-12) and np.all(np.diff(ust) <= 1e-12)  # devirle artmaz


def test_gerilim_artinca_tork_dusmez_akim_artinca_dusuk_hizda_artar(egri):
    n = np.linspace(0, 450, 91)
    assert np.all(egri.alt(n, 12.0, 1.5) >= egri.alt(n, 9.9, 1.5) - 1e-12)
    assert np.all(egri.ust(n, 12.0, 1.5) >= egri.ust(n, 9.9, 1.5) - 1e-12)
    assert egri.alt(30, 12.0, 2.1)[0] == pytest.approx(egri.alt(30, 12.0, 1.5)[0] * 2.1 / 1.5, rel=1e-9)


def test_surucu_akim_limiti_tepedir_etiket_torkunu_vermez(egri):
    """1,5 A'lik sargı 1,5 A tepe akımda etiket torkunun 1/√2'sini verir."""
    s = egri.sargilar[0]
    assert s.K_t * 1.5 == pytest.approx(s.T_tutma / math.sqrt(2))
    assert s.K_t * math.sqrt(2) * s.I_anma == pytest.approx(s.T_tutma)


def test_olcum_girilince_gecici_egri_kullanilmaz(tasarim):
    devir, t9, t12 = [0.0, 100.0, 300.0], [0.25, 0.22, 0.10], [0.25, 0.24, 0.16]
    t = tasarim.degistir({"step_egri.olcum.devir": devir, "step_egri.olcum.tork_9v9": t9, "step_egri.olcum.tork_12v": t12})
    e = step.PullOut(t)
    assert e.alt(100.0, 9.9, 1.5)[0] == pytest.approx(0.22) and e.ust(100.0, 12.0, 1.5)[0] == pytest.approx(0.24)
    assert e.alt(100.0, 10.95, 1.5)[0] == pytest.approx(0.23)
    assert e.alt(400.0, 12.0, 1.5)[0] == 0.0


def test_gerilim_payi_denklemi_ve_birimleri():
    K_t = 0.1886 * ureg("N*m/A")
    I = 1.5 * ureg.A
    R = 2.3 * ureg.ohm
    L = 4.2e-3 * ureg.H
    V = 9.9
    n = step.gerilim_payi_devri(V, 1.5, 0.1886, 2.3, 4.2e-3)
    w = n * 2 * math.pi / 60 * ureg("rad/s")
    E = (K_t * w.to("1/s")).to("V")
    Vr = (I * R).to("V")
    X = (50 * w.to("1/s") * L * I).to("V")
    assert (((E + Vr) ** 2 + X**2) ** 0.5).to("V").magnitude == pytest.approx(V, rel=1e-9)


def test_gerilim_payi_duyarliligi():
    f = step.gerilim_payi_devri
    n0 = f(12.0, 1.5, 0.19, 1.8, 4.2e-3)
    assert f(24.0, 1.5, 0.19, 1.8, 4.2e-3) > n0 > f(9.9, 1.5, 0.19, 1.8, 4.2e-3)
    assert f(12.0, 1.5, 0.19, 1.8, 2.8e-3) > n0 > f(12.0, 1.5, 0.19, 1.8, 6e-3)
    assert f(12.0, 2.1, 0.19, 1.8, 4.2e-3) < n0
    assert f(1.0, 1.5, 0.19, 1.8, 4.2e-3) == 0.0  # I·R gerilimi aşıyor


# -- Adım kaçırma --------------------------------------------------------------------------------
def test_pay_tanimi(egri):
    man = {"n": np.array([50.0, 100.0]), "tau": np.array([0.1, 0.05])}
    p = step.pay(egri, man, 12.0, 1.5)
    assert p["alt"] == pytest.approx(min(egri.alt(50.0, 12.0, 1.5)[0] / 0.1, egri.alt(100.0, 12.0, 1.5)[0] / 0.05))
    assert p["rezonans"] == pytest.approx(egri.rezonans * p["alt"])


def test_manevralarda_motor_hizi_govdeye_goredir(st, ps):
    m = step.manevralar(st)
    assert len(m) == 5
    th0 = math.radians(10)
    y = sim.ivme_girisli_yorunge(ps, sim.referans_toparlanma(ps, th0, st.d("hedef.referans_manevra_suresi")))
    assert m[0]["n"].max() == pytest.approx(np.abs((y["xd"] / ps.r - y["theta_d"]) * 60 / (2 * math.pi)).max())


def test_gecici_egriyle_manevralarda_adim_kacmaz(st, egri, tasarim):
    """Geçici alt eğri, rezonans düşümüyle bile bütün referans manevraları karşılar (boş batarya)."""
    V = tasarim.batarya_gerilimleri()["min"]
    for m in step.manevralar(st):
        assert step.pay(egri, m, V, 1.5)["rezonans"] > 1.0, m["ad"]


def test_a_noktasi_alt_egride_gecer_rezonansta_gecmez(st, egri, tasarim):
    g = motor.gereksinimleri_hesapla(st)
    V = tasarim.batarya_gerilimleri()["min"]
    n, tau = g["nokta_A"]
    a = step.pay(egri, {"n": np.array([n]), "tau": np.array([tau])}, V, 1.5)
    assert a["alt"] > 1.0 and a["rezonans"] < 1.0
    n0, tau0 = g["nokta_A0"]
    assert step.pay(egri, {"n": np.array([n0]), "tau": np.array([tau0])}, V, 1.5)["rezonans"] > 1.0


def test_ivme_siniri_ve_burulma(ps):
    assert step.ivme_siniri(ps, 10.0, 0.7) == pytest.approx(0.7 * ps.g)  # büyük torkta çekiş belirler
    assert step.ivme_siniri(ps, 0.05, 0.7) == pytest.approx(0.1 / (ps.r * model.dogrusal_katsayilar(ps)["M_x"]))
    assert step.burulma_modu(ps, 0.2)["f"] * 2 == pytest.approx(step.burulma_modu(ps, 0.8)["f"], rel=1e-9)  # f ∝ √T
    assert math.degrees(step.yuk_gecikmesi(0.2, 0.2)) == pytest.approx(1.8)  # tepe torkta bir tam adım


# -- Pratik hesaplar -----------------------------------------------------------------------------
def test_adim_frekansi_ve_birimi():
    f = (150 * ureg("turn/min") * (200 * 16 * ureg("1/turn"))).to("Hz")
    assert step.adim_frekansi(150, 16) == pytest.approx(f.magnitude)
    assert step.adim_frekansi(150, 32) == pytest.approx(2 * step.adim_frekansi(150, 16))


def test_mikro_adim_tablosu(tasarim, ps):
    t = step.mikro_adim_tablosu(ps.r, 0.01, (150.0, 300.0), 200.0)
    assert [x["cpr"] for x in t] == [200, 400, 800, 1600, 3200, 6400]
    assert t[4]["ds"] == pytest.approx(2 * math.pi * ps.r / 3200)
    assert max(x["f2"] for x in t) < tasarim.d("surucu.drv8825.f_step_max")


def test_guc_birimleri_ve_degerleri(egri):
    s = egri.sargilar[0]
    g = step.step_guc(s, 1.5, 11.1, 0.5, 2.0)
    P = ((1.5 * ureg.A) ** 2 * (1.8 * ureg.ohm)).to("W")
    assert g["P_bakir"] == pytest.approx(P.magnitude)
    assert g["P_top"] == pytest.approx(2 * (1.5**2 * 1.8 + 1.5**2 * 0.5) + 2.0)
    assert g["I_bat"] == pytest.approx(g["P_top"] / 11.1)
    assert step.pil_suresi(2.45, 11.1, g["P_top"]) == pytest.approx(2.45 * 11.1 / g["P_top"])
    assert step.motor_isinmasi(s, s.I_anma * math.sqrt(2), 80.0) == pytest.approx(80.0)  # iki faz anma akımı
    assert step.step_guc(s, 1.0, 11.1, 0.5, 2.0)["P_bakir"] == pytest.approx(P.magnitude / 2.25)


def test_sigorta_yeterli(st, egri, tasarim):
    V = tasarim.batarya_gerilimleri()
    g = motor.gereksinimleri_hesapla(st)
    n, tau = g["nokta_A"]
    s = egri.sargilar[0]
    assert step.step_guc(s, 1.5, V["min"], 0.64, 2.0, tau, n)["I_bat"] < tasarim.d("elektrik.sigorta")


# -- Pasif test ----------------------------------------------------------------------------------
def test_detent_dusmeyi_engellemez(st, ps):
    temas = yere_degme_acilari(st)
    yd = (temas["ileri"], temas["geri"])
    th0 = math.radians(st.d("sartname.pasif_test_acisi"))
    for sargi in ("robo90", "katalog"):
        T = 2 * st.d(f"step_sargi.{sargi}.detent_torku")
        for i in (1, -1):
            t = sim.detent_dusme(ps, i * th0, T, yd)["t_degme"]
            serbest = sim.acik_cevrim_dusme(ps, i * th0, mod="serbest", yere_degme=yd)["t_degme"]
            kilitli = sim.acik_cevrim_dusme(ps, i * th0, mod="kilitli", yere_degme=yd)["t_degme"]
            assert t is not None and serbest * 0.999 <= t <= kilitli * 1.001
            assert t < st.d("sartname.pasif_test_suresi")


def test_cok_buyuk_detent_kilitli_tekere_yaklasir(st, ps):
    temas = yere_degme_acilari(st)
    yd = (temas["ileri"], temas["geri"])
    th0 = math.radians(10)
    assert sim.detent_dusme(ps, th0, 5.0, yd)["t_degme"] == pytest.approx(
        sim.acik_cevrim_dusme(ps, th0, mod="kilitli", yere_degme=yd)["t_degme"], rel=0.02)


def test_sifir_detent_serbest_tekerle_ayni(st, ps):
    temas = yere_degme_acilari(st)
    yd = (temas["ileri"], temas["geri"])
    th0 = math.radians(10)
    assert sim.detent_dusme(ps, th0, 0.0, yd)["t_degme"] == pytest.approx(
        sim.acik_cevrim_dusme(ps, th0, mod="serbest", yere_degme=yd)["t_degme"], rel=1e-3)
