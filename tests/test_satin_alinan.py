"""Satın alınan motor (JGB37-520 12 V 1000 RPM): veriler, sınama, karar, çözümler ve ölçümle yeniden üretim."""

import math
import subprocess
import sys
from pathlib import Path

import pytest

from denge import motor
from denge import satin_alinan as sa
from denge.parametreler import ek_bolum_mu

KOK = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def G(tasarim):
    return sa.gereksinim_ozeti(tasarim)


@pytest.fixture(scope="module")
def a(tasarim):
    return sa.aday(tasarim)


def test_veri_sayfasi_degerleri_ve_etiketleri(tasarim, a):
    assert (a.bosta_devir, a.reduksiyon, a.ppr, a.durma_akimi) == (1000.0, 10.0, 11, 2.3)
    assert a.durma_torku == pytest.approx(1.6 * motor.KGFCM, rel=1e-3)
    for yol, k in tasarim.kayitlar():
        if yol.startswith("motor_satin_alinan."):
            assert ek_bolum_mu(yol) and k["durum"] in ("doğrulanamadı", "tahmini")
            if k["durum"] == "doğrulanamadı":
                assert "[doğrulanamadı]" in k["kaynak"]
    assert "direnc.net" in tasarim.kayit("motor_satin_alinan.ad")["kaynak"]
    assert sa.olculen_alanlar(tasarim) == []


def test_satici_serisi_1e10_satiri_satin_alinanla_ayni(tasarim, a):
    seri = {round(x.reduksiyon): x for x in motor.satici_serisi_adaylari(tasarim)}
    assert seri[10].bosta_devir == a.bosta_devir and seri[10].durma_torku == pytest.approx(a.durma_torku, rel=1e-3)


def test_sinama_bos_ve_dolu_pil(tasarim, a, G):
    V = tasarim.batarya_gerilimleri()
    bos, dolu = sa.sina(a, G, V["min"]), sa.sina(a, G, V["max"])
    assert bos["sf"] == pytest.approx(1.14, abs=0.01) and dolu["sf"] == pytest.approx(1.50, abs=0.01)
    assert bos["A0"] and not bos["A"] and bos["cekis_orani"] < 1 and bos["B"]
    assert sa.cpr(a) == 440 < G["cpr_min"]
    assert sa.karar(bos, sa.cpr(a), G["cpr_min"], G["SF"]) == "sınırda"
    assert dolu["T_A"] / bos["T_A"] > V["max"] / V["min"]  # tork ve boşta devir birlikte ölçeklenir


def test_karar_olcutu():
    gec = {"sf": 2.1, "B": True}
    assert sa.karar(gec, 1100, 1021, 2.0) == "uygun"
    assert sa.karar(gec, 900, 1021, 2.0) == "sınırda"
    assert sa.karar({"sf": 1.2, "B": True}, 2000, 1021, 2.0) == "sınırda"
    assert sa.karar({"sf": 0.9, "B": True}, 2000, 1021, 2.0) == "uygun değil"
    assert sa.karar({"sf": 3.0, "B": False}, 2000, 1021, 2.0) == "uygun değil"


def test_pwm_orani(a):
    n0, _ = a.egriler(12.0)
    assert motor.pwm_orani(a, 12.0, n0, 0.0) == pytest.approx(1.0, rel=1e-9)  # boşta devirde tam gerilim
    assert motor.pwm_orani(a, 9.9, 100.0, 0.01) == pytest.approx(motor.pwm_orani(a, 12.0, 100.0, 0.01) * 12.0 / 9.9)
    assert motor.pwm_orani(a, 12.0, 100.0, 0.05) > motor.pwm_orani(a, 12.0, 100.0, 0.0)


def test_ek_reduksiyon(a):
    assert sa.ek_reduksiyon(a, 1, 0.9) is a
    b = sa.ek_reduksiyon(a, 3, 0.95)
    assert b.durma_torku == pytest.approx(3 * 0.95 * a.durma_torku) and b.bosta_devir == pytest.approx(a.bosta_devir / 3)
    assert sa.cpr(b) == 3 * sa.cpr(a) == 1320


def test_bir_uc_kayis_uygun_bir_iki_yetmez(tasarim, a):
    rt = {x["k"]: x for x in sa.reduksiyon_taramasi(tasarim, a, [1, 2, 3, 4], tasarim.d("aktarma.kayis_verimi"))}
    assert rt[1]["karar"] == "sınırda" and rt[2]["karar"] == "sınırda" and rt[3]["karar"] == "uygun"
    assert rt[3]["min"]["sf"] >= 2.0 and rt[3]["cpr"] >= 1021
    alt = tasarim.kayit("aktarma.kayis_verimi")["aralik"][0]
    assert {x["k"]: x for x in sa.reduksiyon_taramasi(tasarim, a, [3], alt)}[3]["min"]["sf"] >= 2.0  # verimin alt ucunda da


def test_teker_kuculunce(tasarim, a):
    tt = sa.teker_taramasi(tasarim, a, [0.025, 0.0325])
    k, b = tt
    # Aynı hızda devir ∝ 1/r; referans manevranın tepe hızı da r ile değiştiği için oran biraz daha büyük çıkar
    assert k["nA"] / b["nA"] > 0.0325 / 0.025
    assert k["cekis"] / b["cekis"] == pytest.approx(0.025 / 0.0325, rel=1e-6)
    assert k["cpr_min"] / b["cpr_min"] == pytest.approx(0.025 / 0.0325, rel=1e-6)
    assert k["tA0"] == pytest.approx(b["tA0"])  # el hesabı teker boyutuna bağlı değil
    assert k["sf"] < b["sf"] and k["ref"] > b["ref"]  # iki ölçüt ters yöne gider
    assert k["ileri"] < b["ileri"] and k["yukseklik"] < b["yukseklik"]


def test_kutle_senaryolari(tasarim, a):
    kt = {x["ad"]: x for x in sa.kutle_taramasi(tasarim, a)}
    taban = kt["Şu anki tasarım"]
    assert kt["Batarya alt kata (elektronik yerinde; yer varsa)"]["l"] < taban["l"]
    assert kt["Batarya ve elektronik yer değiştirir"]["l"] > taban["l"]  # elektronik daha ağır kabul edildi
    assert max(x["sf"] for x in kt.values()) < 2.0  # tek başına yetmez
    assert all(x["l"] > 0 for x in kt.values())  # KM aksın üstünde: pasif test korunur


def test_olcum_girilince_karar_yeniden_uretilir(tasarim):
    t = tasarim.degistir({"motor_olcum.bosta_devir": 800.0, "motor_olcum.durma_torku": 0.25, "motor_olcum.cpr_teker": 1320.0})
    assert sa.olculen_alanlar(t) == ["bosta_devir", "durma_torku", "cpr_teker"]
    b = sa.aday(t)
    assert b.gerilim == pytest.approx(t.d("olcum_plani.gerilim")) and b.reduksiyon == pytest.approx(30.0)
    assert b.durma_akimi == pytest.approx(2.3 * 9.9 / 12)  # ölçülmeyen alan ölçüm gerilimine ölçeklenir
    G = sa.gereksinim_ozeti(t)
    s = sa.sina(b, G, t.batarya_gerilimleri()["min"])
    assert sa.karar(s, sa.cpr(b), G["cpr_min"], G["SF"]) == "uygun"


def test_gereken_el_ve_sf_bire_inen_gerilim(tasarim, a, G):
    V = tasarim.batarya_gerilimleri()["min"]
    assert sa.gereken_el(a, G, V, 2.0) == pytest.approx(a.tork(G["nA"], V))
    Vs = sa.sf_bire_inen_gerilim(a, G)
    assert a.tork(G["nA"], Vs) == pytest.approx(G["tA0"], rel=1e-6) and Vs < V


def test_hiz_kestirim_penceresi():
    assert sa.gereken_akim_penceresi(0.0325, 0.02, 1021) == pytest.approx(0.01, rel=1e-3)


def test_komut_satiri_calisir():
    c = subprocess.run([sys.executable, "-m", "denge.motor", "--satin-alinan", "--yan-yana"], cwd=KOK, capture_output=True, text=True, timeout=300)
    assert c.returncode == 0 and "KARAR: SINIRDA" in c.stdout and "1:30" in c.stdout
