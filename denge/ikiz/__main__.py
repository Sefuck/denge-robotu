"""Dijital ikiz komut satırı.

    python -m denge.ikiz                         # ana matris (80 koşu) + motor karşılaştırması: özet tablo ve CSV
    python -m denge.ikiz --senaryo O1-4+ --motor 333 --pil dolu --kontrolcu pid --grafik cikti.png
    python -m denge.ikiz --senaryo O2 --gif o2.gif
    python -m denge.ikiz --lqr-tasarla           # Q, R'den LQI ve dönüş kazançlarını hesaplar (parametre dosyasına yazılır)
    python -m denge.ikiz --pay                   # Ö1-4'te toparlanabilen en büyük eğim, her motor ve pil için
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import numpy as np

from ..parametreler import KOK, Tasarim
from . import cizim, kontrol, toplu
from .ayarlar import MOTOR_ADLARI, govde, ikiz_ayarlari, motorlar
from .senaryolar import SATIN_ALINAN, SENARYO_ADLARI, SENARYO_KODLARI, Kurulum, calistir, degerlendir

CIKTI = KOK / "cikti" / "ikiz"


def lqr_tasarla(t: Tasarim) -> None:
    ay = ikiz_ayarlari(t)
    a = ay.kontrol
    for ad, m in motorlar(t, ay.J_rotor).items():
        p = govde(t, True, m).p
        K = kontrol.lqr_tasarla(p, a.lqr_Q, a.lqr_R, ay.zaman.Ts)
        Kp = kontrol.donus_lqr_tasarla(p, a.lqr_Q_donus, a.lqr_R_donus, ay.zaman.Ts)
        ozd = kontrol.kapali_cevrim_ozdegerleri(p, K, ay.zaman.Ts, 1)
        isaret = "  ← parametre dosyasındaki motor" if ad == SATIN_ALINAN else ""
        print(f"{MOTOR_ADLARI[ad]}{isaret}\n  [kontrol.lqr.K]       deger = [{', '.join(f'{k:.3f}' for k in K)}]"
              f"\n  [kontrol.lqr.K_donus] deger = [{', '.join(f'{k:.3f}' for k in Kp)}]"
              f"\n  bir örnek gecikmeli kapalı çevrimde en büyük |λ| = {np.max(np.abs(ozd)):.4f}")
    print(f"\nDosyadaki K = {list(a.lqr_K)}, K_donus = {list(a.lqr_K_donus)}")


def tek(t: Tasarim, a) -> None:
    k = Kurulum(a.motor, not a.kutusuz, a.pil, a.kontrolcu, a.kestirici)
    ay = ikiz_ayarlari(t)
    t0 = time.time()
    kay = calistir(t, a.senaryo, k, ay)
    d = degerlendir(kay, ay)
    print(f"\n{SENARYO_ADLARI[a.senaryo]} — {k.etiket()}  ({time.time() - t0:.1f} s)")
    for x in d["alt"]:
        print(f"  {x['ad']:12s} {'GEÇTİ' if x['gecti'] else 'KALDI'}  {x['deger']}")
        for ad, ok, deg in x["kosullar"]:
            print(f"      {'✓' if ok else '✗'} {ad}: {deg}")
        for n in x["notlar"]:
            print(f"      not: {n}")
        if x["neden"]:
            print(f"      neden: {x['neden']}")
    o = d["olcutler"]
    print(f"  en büyük eğim {o['en_buyuk_egim']:.1f}°, yere değme payı {o['yere_degme_payi']:.1f}°, doyum {o['doyum_suresi']:.2f} s, "
          f"tepe akım {o['tepe_akim']:.2f} A, kayma {o['kayma_suresi']:.2f} s, kestirim hatası {o['kestirim_hatasi']:.2f}°")
    if a.grafik:
        etiket = f"{k.kontrolcu.upper()} + {k.kestirici}"
        cizim.zaman_grafigi(a.grafik, [(SENARYO_ADLARI[a.senaryo], [(etiket, kay)], {"oteleme": a.senaryo in ("O1-23", "O2")})])
        print(f"  grafik: {a.grafik}")
    if a.gif:
        n = cizim.animasyon(a.gif, kay, t, fps=20, baslik=f"{SENARYO_ADLARI[a.senaryo]} — {k.etiket()}")
        print(f"  animasyon: {a.gif} ({n} kare)")


def matris(t: Tasarim, csv_yolu: Path, tum_grafikler: bool) -> None:
    t0 = time.time()
    isler = list(dict.fromkeys(toplu.ana_isler() + toplu.motor_isleri()))
    sonuclar = toplu.calistir_hepsi(t, isler)
    print(f"{len(sonuclar)} koşu, {time.time() - t0:.0f} s\n")
    print("Satın alınan motor (1000 RPM), alt testler:")
    print("| Kontrolcü + kestirici | Kutu | Pil | " + " | ".join(toplu.ALT_TEST_SIRASI) + " |")
    for ktr in ("lqr", "pid"):
        for kst in ("kalman", "tamamlayici"):
            for kutulu in (True, False):
                for pil in ("dolu", "bos"):
                    r = toplu.alt_test_sonuclari(sonuclar, motor=SATIN_ALINAN, kontrolcu=ktr, kestirici=kst, kutulu=kutulu, pil=pil)
                    print(f"| {ktr.upper()} + {kst} | {'takılı' if kutulu else 'yok'} | {pil} | "
                          + " | ".join("✓" if r[x] else "✗" for x in toplu.ALT_TEST_SIRASI) + " |")
    print("\nMotor karşılaştırması (Kalman; LQR her motora göre aynı Q/R ile tasarlandı):")
    for m in toplu.MOTORLAR:
        for ktr in ("lqr", "pid"):
            r = [v for ku in (True, False) for pil in ("dolu", "bos")
                 for v in toplu.alt_test_sonuclari(sonuclar, motor=m, kontrolcu=ktr, kestirici="kalman", kutulu=ku, pil=pil).values()]
            print(f"  {MOTOR_ADLARI[m]:32s} {ktr.upper()}: {sum(r)}/{len(r)}")
    print("\nKalan alt testler ve nedenleri:")
    for d in sonuclar:
        for x in d["alt"]:
            if not x["gecti"]:
                k = d["kurulum"]
                print(f"  - {x['ad']} [{k['motor']} RPM, {k['kontrolcu']}+{k['kestirici']}, kutu {'takılı' if k['kutulu'] else 'yok'}, {k['pil']}]: {x['neden']}")
    toplu.csv_yaz(csv_yolu, toplu.alt_satirlari(sonuclar))
    print(f"\nCSV: {csv_yolu}")
    if tum_grafikler:
        ay = ikiz_ayarlari(t)
        CIKTI.mkdir(parents=True, exist_ok=True)
        for kod, k in isler:
            kay = calistir(t, kod, k, ay)
            ad = f"{kod}_{k.motor}_{'kutulu' if k.kutulu else 'kutusuz'}_{k.pil}_{k.kontrolcu}_{k.kestirici}.png"
            cizim.zaman_grafigi(CIKTI / ad, [(f"{SENARYO_ADLARI[kod]} — {k.etiket()}", [(k.kontrolcu.upper(), kay)],
                                              {"oteleme": kod in ("O1-23", "O2")})])
        print(f"Grafikler: {CIKTI}/ ({len(isler)} dosya)")


def _ana():
    ap = argparse.ArgumentParser(description="Dijital ikiz: kapalı çevrim simülasyon ve şartname testleri")
    ap.add_argument("--senaryo", choices=SENARYO_KODLARI, help="tek senaryo koştur")
    ap.add_argument("--motor", choices=tuple(MOTOR_ADLARI), default=SATIN_ALINAN)
    ap.add_argument("--kutusuz", action="store_true")
    ap.add_argument("--pil", choices=("dolu", "bos"), default="bos")
    ap.add_argument("--kontrolcu", choices=("lqr", "pid"), default="lqr")
    ap.add_argument("--kestirici", choices=("kalman", "tamamlayici", "ideal"), default="kalman")
    ap.add_argument("--grafik", type=Path, help="tek senaryonun zaman grafiği (PNG)")
    ap.add_argument("--gif", type=Path, help="tek senaryonun 2D animasyonu (GIF)")
    ap.add_argument("--lqr-tasarla", action="store_true")
    ap.add_argument("--pay", action="store_true", help="en büyük toparlanabilen eğim taraması")
    ap.add_argument("--csv", type=Path, default=KOK / "docs" / "simulasyon" / "sonuclar.csv")
    ap.add_argument("--tum-grafikler", action="store_true", help=f"matristeki her koşunun grafiği ({CIKTI.relative_to(KOK)}/, depoya eklenmez)")
    ap.add_argument("--parametreler", default=None)
    a = ap.parse_args()
    t = Tasarim.yukle(a.parametreler)
    if a.lqr_tasarla:
        lqr_tasarla(t)
    elif a.pay:
        pay = toplu.pay_taramasi(t)
        for (m, pil, yon), aci in pay["aci"].items():
            print(f"{MOTOR_ADLARI[m]:32s} {pil:4s} {'+' if yon > 0 else '−'}: {aci:.1f}°   (sınırın üstünde: {pay['neden'][(m, pil, yon)]})")
    elif a.senaryo:
        tek(t, a)
    else:
        matris(t, a.csv, a.tum_grafikler)


if __name__ == "__main__":
    _ana()
