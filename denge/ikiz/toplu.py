"""Senaryo matrisinin toplu (paralel) çalıştırılması, pay taraması ve özet tablolar.

Ana matris (satın alınan motor): 5 senaryo × kutu (takılı/değil) × pil (dolu/boş) × kontrolcü (LQR/PID) × kestirici
(Kalman/tamamlayıcı) = 80 koşu. Motor karşılaştırması: 3 motor × kutu × pil × 5 senaryo, LQR + Kalman.
Pay taraması: Ö1-4'ün toparlanabildiği en büyük başlangıç eğimi (ikiye bölme), her motor ve pil için.
"""

from __future__ import annotations

import csv
import itertools
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ..parametreler import Tasarim
from .ayarlar import DERECE, ikiz_ayarlari, motorlar
from .senaryolar import SATIN_ALINAN, SENARYO_KODLARI, Kurulum, calistir, degerlendir

MOTORLAR = ("1000", "530", "333")


def ana_isler() -> list[tuple[str, Kurulum]]:
    return [(kod, Kurulum(SATIN_ALINAN, kutulu, pil, ktr, kst))
            for ktr, kst, kutulu, pil, kod in itertools.product(("lqr", "pid"), ("kalman", "tamamlayici"), (True, False),
                                                               ("dolu", "bos"), SENARYO_KODLARI)]


def motor_isleri() -> list[tuple[str, Kurulum]]:
    """3 motor × kutu × pil × 5 senaryo × kontrolcü (LQR motora göre yeniden tasarlanır, PID dosyadaki kazançlarla), Kalman."""
    return [(kod, Kurulum(m, kutulu, pil, ktr, "kalman"))
            for m, ktr, kutulu, pil, kod in itertools.product(MOTORLAR, ("lqr", "pid"), (True, False), ("dolu", "bos"), SENARYO_KODLARI)]


# ---------------------------------------------------------------------------
# Paralel çalıştırma (her işçi parametre dosyasının içeriğini alır)
# ---------------------------------------------------------------------------
def _kos(arg) -> dict:
    veri, kod, k, theta0, J_rotor = arg
    t = Tasarim(veri)
    ay = ikiz_ayarlari(t)
    if J_rotor is not None:
        ay = ay.degistir(J_rotor=J_rotor)
    kay = calistir(t, kod, k, ay, theta0=theta0)
    d = degerlendir(kay, ay)
    d["theta0"] = theta0
    return d


def _havuz(isler, paralel: bool):
    if not paralel or len(isler) <= 1:
        return [_kos(i) for i in isler]
    n = min(len(isler), os.cpu_count() or 1)
    with ProcessPoolExecutor(n) as ex:
        return list(ex.map(_kos, isler, chunksize=max(1, len(isler) // (4 * n))))


def calistir_hepsi(t: Tasarim, isler, paralel: bool = True) -> list[dict]:
    return _havuz([(t.veri, kod, k, None, None) for kod, k in isler], paralel)


def pay_taramasi(t: Tasarim, motor_listesi=MOTORLAR, piller=("bos", "dolu"), paralel: bool = True, adim: float = 0.5,
                 ust: float = 45.0, J_rotor: float | None = None) -> dict:
    """Her motor, pil ve yön için Ö1-4'te toparlanabilen en büyük başlangıç eğimi [°] (LQR + Kalman, kutulu).

    İkiye bölme 0° ile `ust` arasında; çözünürlük `adim` derece. Dönen: {"aci": {(motor, pil, yön): derece},
    "neden": {(motor, pil, yön): sınırın hemen üstündeki açıda kalma nedeni}}.
    """
    anahtarlar = [(m, pil, yon) for m in motor_listesi for pil in piller for yon in (1, -1)]
    alt = {a: 0.0 for a in anahtarlar}
    ustd = {a: ust for a in anahtarlar}
    n_adim = math.ceil(math.log2(ust / adim))
    for _ in range(n_adim):
        isler = []
        for a in anahtarlar:
            orta = 0.5 * (alt[a] + ustd[a])
            m, pil, yon = a
            isler.append((t.veri, "O1-4+" if yon > 0 else "O1-4-", Kurulum(m, True, pil, "lqr", "kalman"), yon * orta * DERECE, J_rotor))
        sonuc = _havuz(isler, paralel)
        for a, d in zip(anahtarlar, sonuc):
            orta = 0.5 * (alt[a] + ustd[a])
            if d["gecti"]:
                alt[a] = orta
            else:
                ustd[a] = orta
    # Sınırın hemen üstündeki (ilk kalan) açıda düşme nedeni
    isler = [(t.veri, "O1-4+" if a[2] > 0 else "O1-4-", Kurulum(a[0], True, a[1], "lqr", "kalman"), a[2] * ustd[a] * DERECE, J_rotor)
             for a in anahtarlar]
    nedenler = {a: next((x["neden"] for x in d["alt"] if x["neden"]), "") for a, d in zip(anahtarlar, _havuz(isler, paralel))}
    return {"aci": {a: alt[a] for a in anahtarlar}, "neden": nedenler}


# ---------------------------------------------------------------------------
# Özetler
# ---------------------------------------------------------------------------
def alt_satirlari(sonuclar: list[dict]) -> list[dict]:
    """Her koşunun her alt testi bir satır (CSV ve tablolar için)."""
    satirlar = []
    for d in sonuclar:
        k, o = d["kurulum"], d["olcutler"]
        for a in d["alt"]:
            satirlar.append({
                "senaryo": d["kod"], "alt_test": a["ad"], "motor": k["motor"], "kutu": "takılı" if k["kutulu"] else "yok",
                "pil": k["pil"], "kontrolcu": k["kontrolcu"], "kestirici": k["kestirici"], "sonuc": "GEÇTİ" if a["gecti"] else "KALDI",
                "deger": a["deger"], "en_buyuk_egim_deg": round(o["en_buyuk_egim"], 2), "yere_degme_payi_deg": round(o["yere_degme_payi"], 2),
                "doyum_suresi_s": round(o["doyum_suresi"], 3), "tepe_akim_A": round(o["tepe_akim"], 2), "rms1_akim_A": round(o["rms1_akim"], 2),
                "kayma_suresi_s": round(o["kayma_suresi"], 3), "kutu_gorunur_egim_deg": round(o["kutu_alfa"], 1) if not math.isnan(o["kutu_alfa"]) else "",
                "kestirim_hatasi_rms_deg": round(o["kestirim_hatasi"], 2), "neden": a["neden"] or "", "notlar": "; ".join(a["notlar"]),
            })
    return satirlar


def csv_yaz(yol: Path, satirlar: list[dict]) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(satirlar[0].keys()))
        w.writeheader()
        w.writerows(satirlar)


def bul(sonuclar: list[dict], kod: str, **kosul) -> dict:
    for d in sonuclar:
        if d["kod"] == kod and all(d["kurulum"][a] == b for a, b in kosul.items()):
            return d
    raise KeyError((kod, kosul))


def alt_test_sonuclari(sonuclar: list[dict], **kosul) -> dict[str, bool]:
    """Şartnamenin alt testleri (Ö1-1 … Ö2 sağ) için geçti/kaldı; Ö1-4 iki yön birlikte."""
    out = {}
    for d in sonuclar:
        if all(d["kurulum"][a] == b for a, b in kosul.items()):
            for a in d["alt"]:
                ad = "Ö1-4" if a["ad"].startswith("Ö1-4") else a["ad"]
                out[ad] = out.get(ad, True) and a["gecti"]
    return out


ALT_TEST_SIRASI = ("Ö1-1", "Ö1-2", "Ö1-3", "Ö1-4", "Ö2 ileri", "Ö2 geri", "Ö2 sol 90°", "Ö2 sağ 90°")


def motor_bilgisi(t: Tasarim) -> dict:
    ay = ikiz_ayarlari(t)
    return {k: m for k, m in motorlar(t, ay.J_rotor).items()}
