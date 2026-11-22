"""Dijital ikiz (belge §12): fizik çekirdeği, motor, sensörler, kestirim, kontrol, senaryolar ve geçti/kaldı değerlendirmesi."""

import math
from dataclasses import replace

import numpy as np
import pytest

from denge import model
from denge import simulasyon as sim
from denge.ikiz import ayarlar, kestirim, kontrol, senaryolar as S
from denge.ikiz.fizik import FizikAyarlari, Motor, Robot
from denge.ikiz.sensorler import IMU, enkoder_sayimi
from denge.kutle_merkezi import yere_degme_acilari


@pytest.fixture(scope="module")
def ay(tasarim):
    return ayarlar.ikiz_ayarlari(tasarim)


@pytest.fixture(scope="module")
def mot(tasarim, ay):
    return ayarlar.motorlar(tasarim, ay.J_rotor)


def _fizik(**kw):
    taban = dict(mu=0.7, bosluk=0.0, R_ic=0.15, I_lojik=0.2, surucu_olu_bolge=0.0, pwm_adimi=1 / 1023, dt=1e-4)
    return FizikAyarlari(**(taban | kw))


def _surtunmesiz(m: Motor, J_m=None) -> Motor:
    return replace(m, I0=0.0, J_m=m.J_m if J_m is None else J_m)


# ---------------------------------------------------------------------------
# Fizik çekirdeği
# ---------------------------------------------------------------------------
def test_kisitlar_etkinken_lagrange_modeliyle_ayni_ivmeler(p, mot):
    """Teker tutunurken, dişli temasta ve rotor sürtünmesizken ivmeler model.dinamik ile aynı (J_m, b > 0)."""
    pp = p.degistir(J_m=4e-4, b=0.003)
    m = _surtunmesiz(mot["1000"], 4e-4)
    rng = np.random.default_rng(1)
    for _ in range(6):
        r = Robot(pp, m, _fizik(mu=10.0), theta0=rng.uniform(-0.6, 0.6))
        v, w, thd = rng.uniform(-1, 1, 3)
        wR, wL = v / pp.r + pp.d / (2 * pp.r) * w, v / pp.r - pp.d / (2 * pp.r) * w
        r.nu = [v, w, thd, wR, wL, wR, wL]
        tR, tL = rng.uniform(-0.2, 0.2, 2)
        beklenen = model.dinamik(pp, [0, v, r.q[2], thd, 0, w], tR, tL)
        nu0 = list(r.nu)
        r.mekanik_adim(tR, tL)
        ivme = [(r.nu[i] - nu0[i]) / r.dt for i in range(3)]
        assert ivme == pytest.approx([beklenen[1], beklenen[5], beklenen[3]], abs=1e-8)
        assert all(r.etkin[i] for i in (0, 1, 4, 5)) and r.dongu_asimi == 0


def test_serbest_dusme_acik_cevrim_simulasyonuyla_ortusur(p, mot):
    """u = 0, serbest teker: ikizin düşmesi §3.7'deki solve_ivp düşmesiyle aynı (yarı örtük Euler, dt = 0,5 ms)."""
    m = _surtunmesiz(mot["1000"], 0.0)
    r = Robot(p, m, _fizik(dt=5e-4, mu=10.0), theta0=math.radians(10))
    ref = sim.acik_cevrim_dusme(p, math.radians(10), t_son=0.3)
    th = []
    for _ in range(600):
        r.mekanik_adim(0.0, 0.0)
        th.append(r.q[2])
    beklenen = np.interp(np.arange(1, 601) * 5e-4, ref["t"], ref["theta"])
    n = min(len(th), int(ref["t"][-1] / 5e-4))
    assert np.max(np.abs(np.array(th[:n]) - beklenen[:n])) < math.radians(0.3)


def test_motor_sabitleri_veri_sayfasiyla_tutarli(tasarim, mot):
    """Boşta kararlı devir = veri sayfasındaki devir (12 V); durma akımı = V/R; sürtünme = K_t I0."""
    for ad, n0 in (("1000", 1000.0), ("530", 530.0), ("333", 333.0)):
        m = mot[ad]
        assert m.kararli_devir(12.0) * 60 / (2 * math.pi) == pytest.approx(n0, rel=1e-6)
        assert 12.0 / m.R == pytest.approx(2.3, rel=1e-6)
        assert m.tau_f == pytest.approx(m.K_t * 0.12)
        assert m.cpr == 4 * 11 * m.N
    # Yansıyan atalet N² ile büyür
    assert mot["333"].J_m / mot["1000"].J_m == pytest.approx(9.0)


def test_kilitlenmede_akim_ve_pil_gerilim_dusumu(p, mot):
    m = mot["1000"]
    r = Robot(p, m, _fizik())
    tR, _ = r.elektrik(1.0, 1.0, 12.6)
    beklenen_V = (12.6 - 0.15 * 0.2) / (1 + 0.15 * 2 / m.R)
    assert r.V_bara == pytest.approx(beklenen_V)
    assert r.akim[0] == pytest.approx(beklenen_V / m.R)
    assert tR == pytest.approx(m.K_t * beklenen_V / m.R)


def test_cekis_siniri_asilinca_teker_kayar_ve_surtunme_mu_N(p, mot):
    m = _surtunmesiz(mot["1000"])
    r = Robot(p, m, _fizik(mu=0.05, dt=5e-4))
    for _ in range(20):
        r.mekanik_adim(0.15, 0.15)
    assert r.kayiyor(0) and r.kayiyor(1)
    assert abs(r.F[0]) == pytest.approx(0.05 * r.N[0], rel=1e-9)
    # Yüksek sürtünmede aynı tork kaydırmaz
    r2 = Robot(p, m, _fizik(mu=0.9, dt=5e-4))
    for _ in range(20):
        r2.mekanik_adim(0.15, 0.15)
    assert not r2.kayiyor(0) and abs(r2.F[0]) < 0.9 * r2.N[0]


def test_disli_boslugu_bosluk_icinde_kalir_ve_enkoder_rotoru_gorur(p, mot):
    m = mot["1000"]
    beta = 0.035 / 2
    r = Robot(p.degistir(J_m=m.J_m), m, _fizik(bosluk=0.035, dt=5e-4))
    deltalar, temas = [], []
    for k in range(4000):
        tau = 0.03 * math.copysign(1.0, math.sin(2 * math.pi * 2 * k * 5e-4))
        r.mekanik_adim(tau, tau)
        deltalar.append(r.bosluk_konumu(0))
        temas.append(r.disli_temasta(0))
    d = np.array(deltalar)
    assert np.all(np.abs(d) <= beta + 1e-12)
    assert d.max() == pytest.approx(beta) and d.min() == pytest.approx(-beta)
    assert 0 < np.mean(temas) < 1  # yön değiştikçe boşluktan geçer
    # Enkoder rotoru sayar: teker ile rotor açısı arasındaki fark boşluk kadar olabilir
    assert abs(r.bagil_aci(0) - (r.q[3] - r.q[2])) <= beta + 1e-12


def test_surucu_olu_bolge_ve_pwm_cozunurlugu(p, mot):
    r = Robot(p, mot["1000"], _fizik(surucu_olu_bolge=0.02))
    assert r.surucu(0.015) == 0.0 and r.surucu(1.7) == 1.0 and r.surucu(-1.7) == -1.0
    assert r.surucu(0.5) == pytest.approx(round(0.5 * 1023) / 1023)


# ---------------------------------------------------------------------------
# Sensörler ve kestirim
# ---------------------------------------------------------------------------
def test_imu_gurultusu_ve_sapmasi_veri_sayfasiyla_tutarli(ay):
    dt = 5e-4
    imu = IMU(ay.sensor, dt, np.random.default_rng(3), 9.80665)
    g, ax = [], []
    for _ in range(40000):
        imu.guncelle(0.0, 0.0, 0.0, 0.0)
        o = imu.oku()
        g.append(o[0])
        ax.append(o[1])
    g = np.array(g[2000:])
    beklenen_std = ay.sensor.gyro_gurultu * math.sqrt(math.pi / 2 * ay.sensor.suzgec_hz)
    assert np.std(g) == pytest.approx(beklenen_std, rel=0.25)
    assert np.mean(g) == pytest.approx(imu.gyro_sapma, abs=3 * beklenen_std)
    assert abs(imu.gyro_sapma) == pytest.approx(ay.sensor.gyro_sapma)
    assert np.mean(ax[2000:]) == pytest.approx(imu.ivme_sapma, abs=0.005)


def test_ivmeolcer_durgunken_egimi_hizlanirken_a_bolu_g_hatasini_verir(ay):
    imu = IMU(replace(ay.sensor, gyro_gurultu=0.0, ivme_gurultu=0.0, ivme_sapma=0.0, gyro_sapma=0.0, imu_konum=(0.0, 0.0)),
              5e-4, np.random.default_rng(0), 9.80665)
    for _ in range(200):
        imu.guncelle(math.radians(5), 0.0, 0.0, 0.0)
    _, ax_, az_ = imu.oku()
    assert math.degrees(kestirim.ivme_acisi(ax_, az_)) == pytest.approx(5.0, abs=0.01)
    for _ in range(400):
        imu.guncelle(0.0, 0.0, 0.0, 2.0)
    _, ax_, az_ = imu.oku()
    assert kestirim.ivme_acisi(ax_, az_) == pytest.approx(-math.atan(2.0 / 9.80665), abs=1e-3)


def test_enkoder_nicemlemesi():
    cpr = 440
    adim = 2 * math.pi / cpr
    assert [enkoder_sayimi(k * adim + 1e-9, cpr) for k in (-3, 0, 1, 7)] == [-3, 0, 1, 7]
    assert enkoder_sayimi(0.999 * adim, cpr) == 0


def test_kalman_jiroskop_sapmasini_kestirir_tamamlayici_aciya_yakinsar():
    T, b, aci = 0.005, math.radians(0.5), 0.1
    rng = np.random.default_rng(0)
    kf = kestirim.KalmanSuzgeci(0.001, 3e-5, 0.03, T)
    tf = kestirim.TamamlayiciSuzgec(0.5, T)
    kf.baslat(0.0)
    tf.baslat(0.0)
    for _ in range(12000):
        olcum = aci + 0.01 * rng.standard_normal()
        kf.guncelle(b, olcum)
        tf.guncelle(b, olcum)
    assert kf.sapma == pytest.approx(b, rel=0.1)
    assert kf.aci == pytest.approx(aci, abs=0.005)
    assert tf.aci == pytest.approx(aci + b * 0.5, abs=0.005)  # tamamlayıcıda kalıcı hata = sapma × τ


def test_tasinabilir_siniflar_sabit_alanli():
    """ESP32'ye taşınacak sınıflar __slots__ ile sabit alanlıdır (C yapısı gibi; çalışırken alan eklenemez)."""
    for sinif in (kestirim.TamamlayiciSuzgec, kestirim.KalmanSuzgeci, kestirim.DurumKestirici, kontrol.PIDKontrolcu,
                  kontrol.LQRKontrolcu, kontrol.CikisKati, kontrol.Referans, kontrol.Profil, kontrol.Suzgec2):
        assert "__slots__" in sinif.__dict__, sinif
    k = kestirim.TamamlayiciSuzgec(0.5, 0.005)
    with pytest.raises(AttributeError):
        k.yeni_alan = 1


# ---------------------------------------------------------------------------
# Kontrol
# ---------------------------------------------------------------------------
def test_kontrolculer_ayni_arayuz_ve_kazanclar_dosyadan(tasarim, ay):
    s = [0.01, 0.02, ay.kontrol.denge_acisi + 0.03, 0.1, 0.05, 0.0]
    ref = [0.0] * 6
    for yontem in ("lqr", "pid"):
        k = kontrol.kontrolcu_olustur(ay.kontrol, ay.zaman.Ts, yontem)
        u, u_psi = k.hesapla(s, ref)
        assert isinstance(u, float) and isinstance(u_psi, float)
        assert u > 0  # öne eğilen gövde: teker ileri
        assert u_psi < 0  # sola dönmüş (ψ > 0): sağa düzelt
    lqr = kontrol.LQRKontrolcu(ay.kontrol, ay.zaman.Ts)
    assert (lqr.K1, lqr.K2, lqr.K3, lqr.K4, lqr.K5) == tuple(tasarim.d("kontrol.lqr.K"))
    pid = kontrol.PIDKontrolcu(ay.kontrol, ay.zaman.Ts)
    assert (pid.Kp, pid.Ki, pid.Kd) == tuple(tasarim.d("kontrol.pid.aci"))


def test_dosyadaki_lqi_kazanclari_tasarimla_tutarli_ve_gecikmeyle_kararli(tasarim, ay, mot):
    a = ay.kontrol
    p = ayarlar.govde(tasarim, True, mot["1000"]).p
    K = kontrol.lqr_tasarla(p, a.lqr_Q, a.lqr_R, ay.zaman.Ts)
    assert np.allclose(a.lqr_K, K, rtol=0.02, atol=1e-3), "parametreler değişti: python -m denge.ikiz --lqr-tasarla"
    for kutulu in (True, False):
        pk = ayarlar.govde(tasarim, kutulu, mot["1000"]).p
        for gecikme in (0, 1):
            assert np.max(np.abs(kontrol.kapali_cevrim_ozdegerleri(pk, a.lqr_K, ay.zaman.Ts, gecikme))) < 1.0


def test_cikis_kati_akim_siniri_ve_surekli_olu_bolge_telafisi(ay, mot):
    c = kontrol.CikisKati(mot["1000"], ay.kontrol, ay.zaman.Ts)
    c.pil_olcumu(11.0)
    d = [c.hesapla(tau, 0.0, 0.0, 0.0)[0] for tau in np.linspace(-0.02, 0.02, 401)]
    assert np.max(np.abs(np.diff(d))) < 0.01  # sıfırda sıçrama yok
    assert c.hesapla(0.0, 0.0, 0.0, 0.0)[0] == 0.0
    c.hesapla(5.0, 0.0, 0.0, 0.0)
    assert c.doyum_akim and abs(c.d[0]) <= 1.0


def test_referans_profili_mesafeyi_tamamlar_ve_durur():
    r = kontrol.Referans(0.25, 0.005, 0.1)
    r.komut(0.0, "ileri", 1.0, 4.0)
    for k in range(1600):
        out = r.hesapla(k * 0.005)
    assert out[0] == pytest.approx(1.0, abs=1e-3) and abs(out[1]) < 1e-3
    r.komut(8.0, "sol", math.pi / 2, 2.0)
    for k in range(1600, 2800):
        out = r.hesapla(k * 0.005)
    assert out[3] == pytest.approx(math.pi / 2, abs=1e-3)


# ---------------------------------------------------------------------------
# Senaryolar ve değerlendirme
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kod,kontrolcu", [("O1-4+", "lqr"), ("O1-4-", "pid"), ("O2", "lqr")])
def test_satin_alinan_motor_temel_senaryolari_gecer(tasarim, ay, kod, kontrolcu):
    k = S.Kurulum("1000", True, "bos", kontrolcu, "kalman")
    d = S.degerlendir(S.calistir(tasarim, kod, k, ay), ay)
    assert d["gecti"], [a["neden"] for a in d["alt"]]
    assert d["olcutler"]["yere_degme_payi"] > 30


def test_statik_denge_30_s(tasarim, ay):
    d = S.degerlendir(S.calistir(tasarim, "O1-1", S.Kurulum(kestirici="tamamlayici"), ay), ay)
    assert d["gecti"] and d["olcutler"]["sure"] >= 30.0


def test_kontrolsuz_robot_duser_ve_neden_yazilir(tasarim, ay):
    sifir = ay.degistir(kontrol=replace(ay.kontrol, lqr_K=(0.0,) * 5, ileri_besleme_acik=False))
    kay = S.calistir(tasarim, "O1-4+", S.Kurulum(), sifir)
    d = S.degerlendir(kay, sifir)
    assert kay.dustu and not d["gecti"]
    yd = math.degrees(yere_degme_acilari(tasarim)["ileri"])
    assert math.degrees(kay.k("theta")[-1]) == pytest.approx(yd, abs=1.0)
    assert "yere değdi" in d["alt"][0]["neden"] and "Neden:" in d["alt"][0]["neden"]


def test_ivme_telafisi_olmadan_toparlanma_kotulesir(tasarim, ay):
    telafisiz = ay.degistir(kestirim=replace(ay.kestirim, ivme_telafisi=False))
    a = S.degerlendir(S.calistir(tasarim, "O1-4+", S.Kurulum(), ay), ay)["olcutler"]["kestirim_hatasi"]
    b = S.degerlendir(S.calistir(tasarim, "O1-4+", S.Kurulum(), telafisiz), telafisiz)["olcutler"]["kestirim_hatasi"]
    assert b > 1.5 * a


def test_senaryolar_tekrarlanabilir(tasarim, ay):
    k = S.Kurulum(pil="dolu")
    a = S.calistir(tasarim, "O1-4-", k, ay, sure=2.0)
    b = S.calistir(tasarim, "O1-4-", k, ay, sure=2.0)
    assert np.array_equal(a.veri, b.veri)


def test_fizik_adimi_yakinsar(tasarim, ay):
    """dt yarıya inince (gerçek durumla, boşluksuz) Ö1-4 eğim yörüngesi 0,5°'den az değişir."""
    taban = ay.degistir(fizik=replace(ay.fizik, bosluk=0.0))
    ince = taban.degistir(fizik=replace(taban.fizik, dt=taban.fizik.dt / 2))
    k = S.Kurulum(kestirici="ideal")
    a = S.calistir(tasarim, "O1-4+", k, taban, sure=1.5)
    b = S.calistir(tasarim, "O1-4+", k, ince, sure=1.5)
    n = min(len(a.veri), len(b.veri))
    assert np.max(np.abs(a.k("theta")[:n] - b.k("theta")[:n])) < math.radians(0.5)


def test_degerlendirici_kutu_ve_durma_olcutlerini_uygular(tasarim, ay):
    kay = S.calistir(tasarim, "O1-1", S.Kurulum(), ay, sure=31.0)
    kay.veri[:, S.K["alfa_kutu"]] = math.radians(80)  # kutu devrilir
    d = S.degerlendir(kay, ay)
    kosul = dict((ad, ok) for ad, ok, _ in d["alt"][0]["kosullar"])
    assert not d["gecti"] and kosul["Kutu düşmez"] is False and "Kutu düşmez" in d["alt"][0]["neden"]
    kutusuz = S.calistir(tasarim, "O1-1", S.Kurulum(kutulu=False), ay, sure=31.0)
    assert all(ad != "Kutu düşmez" for ad, _, _ in S.degerlendir(kutusuz, ay)["alt"][0]["kosullar"])


def test_aday_motorda_lqr_motora_gore_yeniden_tasarlanir(tasarim, ay, mot):
    p = ayarlar.govde(tasarim, True, mot["333"]).p
    yeni = kontrol.motora_gore_tasarla(ay.kontrol, p, ay.zaman.Ts)
    assert yeni.lqr_K != ay.kontrol.lqr_K and abs(yeni.lqr_K[3]) > abs(ay.kontrol.lqr_K[3])  # büyük J_m → büyük θ̇ kazancı
    assert yeni.pid_aci == ay.kontrol.pid_aci


def test_sinirsiz_kisit_tutunmaz_ve_surtunmesiz_motorda_cikis_kati_calisir(p, mot, ay):
    """Sürtünmesiz rotor (τ_f = 0) hiçbir adımda gövdeye kilitlenmez; boşta akımı sıfır motorda çıkış katı bölme hatası vermez."""
    m = _surtunmesiz(mot["1000"])
    r = Robot(p.degistir(J_m=m.J_m), m, _fizik(dt=5e-4))
    for k in range(400):
        tau = 0.02 * math.sin(2 * math.pi * 3 * k * 5e-4)
        r.mekanik_adim(tau, tau)
        assert not r.etkin[2] and not r.etkin[3]
    c = kontrol.CikisKati(m, ay.kontrol, ay.zaman.Ts)
    c.pil_olcumu(11.0)
    assert c.hesapla(0.01, 0.0, 0.0, 0.0)[0] > 0


def test_o5_senaryosu_python_ikizinde_gecer(tasarim, ay):
    sen = S.senaryolar(ay)["O5"]
    assert [a.tur for a in sen.alt_testler] == ["statik", "hedef", "hedef"]
    assert sen.alt_testler[1].hedef == pytest.approx((1.0, 0.5)) and sen.alt_testler[2].hedef == pytest.approx((0.0, 0.5), abs=1e-9)
    assert sen.alt_testler[1].pencere[1] - sen.alt_testler[1].pencere[0] == pytest.approx(5.0)  # hedefte kutuyla 5 s
    d = S.degerlendir(S.calistir(tasarim, "O5", S.Kurulum(), ay), ay)
    assert d["gecti"], [a["neden"] for a in d["alt"]]
    assert "O5" not in S.SENARYO_KODLARI  # §12 ana matrisi değişmedi


def test_oneri_secenekleri_varsayilanda_kapali_acilinca_2d_gecer(tasarim, ay):
    assert ay.kestirim.sapma_jiroskopla is False and ay.kontrol.donus_integrali == 0.0
    oneri = ay.degistir(kestirim=replace(ay.kestirim, sapma_jiroskopla=True),
                        kontrol=replace(ay.kontrol, donus_integrali=ay.kontrol.oneri3d_donus_integrali))
    d = S.degerlendir(S.calistir(tasarim, "O2", S.Kurulum(), oneri), oneri)
    assert d["gecti"], [a["neden"] for a in d["alt"]]
