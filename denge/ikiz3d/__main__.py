"""3D dijital ikiz (MuJoCo) komut satırı.

    python -m denge.ikiz3d --senaryo O1-4+                         # tek senaryo, sonuç ve ölçütler
    python -m denge.ikiz3d --senaryo O2 --oneri --video o2.mp4       # öneri ayarlarıyla, yan + çapraz MP4
    mjpython -m denge.ikiz3d --senaryo O1-23 --canli                 # canlı izleme (macOS'ta mjpython gerekir)
    python -m denge.ikiz3d --karsilastir                            # 2D ve 3D yan yana (§12.11 tablosu)
    python -m denge.ikiz3d --sunum                                  # toplantı videoları → docs/video/
    python -m denge.ikiz3d --tum-videolar                           # bütün senaryolar × pil → cikti/video/ (depoya eklenmez)
    python -m denge.ikiz3d --mjcf model.xml                         # üretilen MJCF'i yazar (MuJoCo'nun kendi görüntüleyicisi için)
"""

from __future__ import annotations

import argparse
import math
import platform
import time
from pathlib import Path

from ..ikiz.ayarlar import MOTOR_ADLARI, ikiz_ayarlari, motorlar
from ..ikiz.senaryolar import SENARYO_ADLARI, TUM_SENARYOLAR, Kurulum
from ..parametreler import KOK, Tasarim
from . import karsilastirma, mjcf, video
from .kosucu import calistir3d, degerlendir3d

VIDEO_DIZINI = KOK / "docs" / "video"
TUM_VIDEO_DIZINI = KOK / "cikti" / "video"

# Toplantı seti: (dosya, senaryo, öneri ayarları mı, oynatma hızı, süre sınırı)
SUNUM = (
    ("o1_4_arti_10.mp4", "O1-4+", False, 0.5, 5.0),
    ("o1_4_eksi_10.mp4", "O1-4-", False, 0.5, 5.0),
    ("o1_23_kutulu.mp4", "O1-23", False, 1.0, None),
    ("o2_varsayilan.mp4", "O2", False, 1.0, None),
    ("o2_oneri.mp4", "O2", True, 1.0, None),
    ("o5_oneri.mp4", "O5", True, 1.0, None),
)


def _etiket(k: Kurulum, oneri: bool) -> str:
    return (f"{k.motor} RPM, {'boş' if k.pil == 'bos' else 'dolu'} pil, {'kutulu' if k.kutulu else 'kutusuz'} · "
            f"{'LQI' if k.kontrolcu == 'lqr' else 'PID'} + {'Kalman' if k.kestirici == 'kalman' else 'tamamlayıcı'}"
            + (" · öneri: sapma z jiroskobuyla, dönüşte integral" if oneri else ""))


def video_kaydet(t, kod: str, k: Kurulum, oneri: bool, yol: Path, hiz: float = 1.0, t_son: float | None = None) -> dict:
    import mujoco

    ay = ikiz_ayarlari(t)
    if oneri:
        ay = karsilastirma.oneri_ayarlari(ay)
    fps = int(t.d("simulasyon.video_fps"))
    kay = calistir3d(t, kod, k, ay, video_fps=fps / hiz * 1.0 + 1e-9)
    d = degerlendir3d(kay, ay)
    m = mujoco.MjModel.from_xml_string(mjcf.mjcf(t, motorlar(t, ay.J_rotor)[k.motor], ay, k.kutulu))
    n = video.mp4_yaz(yol, m, kay.kareler, SENARYO_ADLARI[kod].split(" (")[0].replace("Ö1-4 +10°", "Ö1-4: +10°").replace("Ö1-4 −10°", "Ö1-4: −10°"),
                      _etiket(k, oneri), "GEÇTİ" if d["gecti"] else "KALDI", hiz=hiz, fps=fps, t_son=t_son)
    return {"kare": n, "gecti": d["gecti"], "yol": yol, "boyut": yol.stat().st_size}


def canli(t, kod: str, k: Kurulum, oneri: bool) -> None:
    import mujoco.viewer

    ay = ikiz_ayarlari(t)
    if oneri:
        ay = karsilastirma.oneri_ayarlari(ay)
    durum = {"izleyici": None, "t0": None, "i": 0}

    def geri_cagir(m, d, t_sim):
        if durum["izleyici"] is None:
            try:
                durum["izleyici"] = mujoco.viewer.launch_passive(m, d)
            except RuntimeError as e:
                if platform.system() == "Darwin":
                    raise SystemExit("macOS'ta canlı izleme mjpython ister:\n  .venv/bin/mjpython -m denge.ikiz3d "
                                     f"--senaryo {kod} --canli") from e
                raise
            durum["t0"] = time.time()
        iz = durum["izleyici"]
        if not iz.is_running():
            return True
        durum["i"] += 1
        if durum["i"] % 4 == 0:  # ≈ 50 Hz görüntü
            iz.sync()
            bekle = t_sim - (time.time() - durum["t0"])
            if bekle > 0:
                time.sleep(bekle)
        return False

    kay = calistir3d(t, kod, k, ay, geri_cagir=geri_cagir)
    d = degerlendir3d(kay, ay)
    print(f"{SENARYO_ADLARI[kod]}: {'GEÇTİ' if d['gecti'] else 'KALDI'}  " + "  ".join(f"{a['ad']}: {a['deger']}" for a in d["alt"]))
    iz = durum["izleyici"]
    while iz is not None and iz.is_running():  # pencere kapatılana kadar son durum
        iz.sync()
        time.sleep(0.05)


def tek(t, a) -> None:
    k = Kurulum(a.motor, not a.kutusuz, a.pil, a.kontrolcu, a.kestirici)
    ay = ikiz_ayarlari(t)
    if a.oneri:
        ay = karsilastirma.oneri_ayarlari(ay)
    t0 = time.time()
    kay = calistir3d(t, a.senaryo, k, ay)
    d = degerlendir3d(kay, ay)
    print(f"\n{SENARYO_ADLARI[a.senaryo]} (3D) — {_etiket(k, a.oneri)}  ({time.time() - t0:.1f} s)")
    for x in d["alt"]:
        print(f"  {x['ad']:40s} {'GEÇTİ' if x['gecti'] else 'KALDI'}  {x['deger']}")
        for ad, ok, deg in x["kosullar"]:
            print(f"      {'✓' if ok else '✗'} {ad}: {deg}")
        if x["neden"]:
            print(f"      neden: {x['neden']}")
    o = d["olcutler"]
    print(f"  en büyük eğim {o['en_buyuk_egim']:.1f}°, doyum {o['doyum_suresi']:.2f} s, tepe akım {o['tepe_akim']:.2f} A, "
          f"teker kayması {o['kayma_suresi']:.2f} s, kestirim hatası {o['kestirim_hatasi']:.2f}°")
    if kay.dustu and kay.temas_aci is not None:
        print(f"  gövde {kay.t_dusme:.2f} s'de {math.degrees(kay.temas_aci):.1f}° eğimde zemine değdi")


def _ana():
    ap = argparse.ArgumentParser(description="3D dijital ikiz (MuJoCo)")
    ap.add_argument("--senaryo", choices=TUM_SENARYOLAR)
    ap.add_argument("--motor", choices=tuple(MOTOR_ADLARI), default="1000")
    ap.add_argument("--kutusuz", action="store_true")
    ap.add_argument("--pil", choices=("dolu", "bos"), default="bos")
    ap.add_argument("--kontrolcu", choices=("lqr", "pid"), default="lqr")
    ap.add_argument("--kestirici", choices=("kalman", "tamamlayici"), default="kalman")
    ap.add_argument("--oneri", action="store_true", help="sapmayı z jiroskobuyla kestir, dönüşe integral ekle (§12.11)")
    ap.add_argument("--video", type=Path, help="MP4 (yan + çapraz)")
    ap.add_argument("--hiz", type=float, default=1.0, help="video oynatma hızı (0,5 = yarı hız)")
    ap.add_argument("--canli", action="store_true", help="canlı izleme (macOS: mjpython)")
    ap.add_argument("--karsilastir", action="store_true")
    ap.add_argument("--sunum", action="store_true", help=f"toplantı videoları → {VIDEO_DIZINI.relative_to(KOK)}/")
    ap.add_argument("--tum-videolar", action="store_true", help=f"→ {TUM_VIDEO_DIZINI.relative_to(KOK)}/")
    ap.add_argument("--mjcf", type=Path)
    ap.add_argument("--parametreler", default=None)
    a = ap.parse_args()
    t = Tasarim.yukle(a.parametreler)
    if a.mjcf:
        ay = ikiz_ayarlari(t)
        a.mjcf.write_text(mjcf.mjcf(t, motorlar(t, ay.J_rotor)[a.motor], ay, not a.kutusuz), encoding="utf-8")
        print(f"MJCF: {a.mjcf}")
    elif a.karsilastir:
        r = karsilastirma.karsilastir(t)
        print(karsilastirma.tablo(r))
        f = karsilastirma.farklar(r)
        print(f"\nGeçen alt test: " + ", ".join(f"{karsilastirma.VARYANTLAR[b]} {f['gecen'][b]}/{f['sayi'][b]}" for b in karsilastirma.VARYANTLAR))
        print("\n".join(f"  - {x}" for x in f["farkli"]))
    elif a.sunum or a.tum_videolar:
        isler = ([(VIDEO_DIZINI / ad, kod, oneri, hiz, ts, "bos") for ad, kod, oneri, hiz, ts in SUNUM] if a.sunum else
                 [(TUM_VIDEO_DIZINI / f"{kod}_{pil}.mp4", kod, False, 0.5 if kod.startswith("O1-4") else 1.0, None, pil)
                  for kod in TUM_SENARYOLAR for pil in ("dolu", "bos")])
        for yol, kod, oneri, hiz, ts, pil in isler:
            t0 = time.time()
            r = video_kaydet(t, kod, Kurulum("1000", True, pil, "lqr", "kalman"), oneri, yol, hiz, ts)
            print(f"{yol.relative_to(KOK)}: {'GEÇTİ' if r['gecti'] else 'KALDI'}, {r['kare']} kare, {r['boyut'] / 1e6:.1f} MB, {time.time() - t0:.0f} s")
    elif a.senaryo:
        k = Kurulum(a.motor, not a.kutusuz, a.pil, a.kontrolcu, a.kestirici)
        if a.canli:
            canli(t, a.senaryo, k, a.oneri)
        elif a.video:
            r = video_kaydet(t, a.senaryo, k, a.oneri, a.video, a.hiz)
            print(f"{a.video}: {'GEÇTİ' if r['gecti'] else 'KALDI'}, {r['kare']} kare, {r['boyut'] / 1e6:.1f} MB")
        else:
            tek(t, a)
    else:
        ap.print_help()


if __name__ == "__main__":
    _ana()
