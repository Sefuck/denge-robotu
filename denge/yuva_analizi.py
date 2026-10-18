"""İlaç kutusu yuvası ve kütle merkezi analizleri (model ve simülasyona dayanır).

tasarim argümanı parametreler.Tasarim nesnesidir.
"""

from __future__ import annotations

import math

import numpy as np

from . import model, motor, simulasyon
from .kutle_merkezi import denge_acisi, ozgul_kuvvet, vurus_merkezi, yere_degme_acilari

YUVA_ETIKETLERI = {"ust": "Üst plaka", "orta": "Orta kat", "alt": "Alt kat"}


def durum_ozeti(tasarim, etiket: str, **kw) -> dict:
    """Bir yük/yerleşim durumu için KM, kutuplar, torklar ve düşme süresi."""
    p = tasarim.model(**kw)
    g = tasarim.govde(**kw)
    th0 = math.radians(tasarim.d("sartname.toparlanma_acisi"))
    temas = yere_degme_acilari(tasarim)
    dusme = simulasyon.acik_cevrim_dusme(p, th0, mod="serbest", yere_degme=(temas["ileri"], temas["geri"]))
    return {
        "etiket": etiket,
        "m_b": p.m_b,
        "m_toplam": g.kutle + 2 * p.m_w,
        "x_c": g.km[0],
        "z_c": g.km[2],
        "l": p.l,
        "trim": math.degrees(denge_acisi(g.km)),
        "p_serbest": model.kararsiz_kutup(p),
        "p_kilitli": model.kilitli_kutup(p),
        "kok_g_l": math.sqrt(p.g / p.l) if p.l > 0 else 0.0,
        "tau_statik": p.m_b * p.g * p.l * math.sin(th0),
        "tau_tutma": motor.tutma_torku_tam(p, th0),
        "t_dusme": dusme["t_degme"],
        "z_cp": vurus_merkezi(p),
    }


def com_karsilastirma(tasarim) -> list[dict]:
    """Her yuva seçeneği için kutusuz ve kutulu durum; değişimler aynı seçeneğin kutusuz hâline göre."""
    satirlar = []
    for yuva, etiket in YUVA_ETIKETLERI.items():
        kutusuz = durum_ozeti(tasarim, f"{etiket}, kutusuz", kutulu=False, yuva=yuva) | {"yuva": yuva, "kutulu": False}
        kutulu = durum_ozeti(tasarim, f"{etiket}, kutulu", kutulu=True, yuva=yuva) | {"yuva": yuva, "kutulu": True}
        for s in (kutusuz, kutulu):
            s["dl"] = s["l"] - kutusuz["l"]
            s["dp_yuzde"] = 100 * (s["p_serbest"] / kutusuz["p_serbest"] - 1)
            s["dtau_yuzde"] = 100 * (s["tau_statik"] / kutusuz["tau_statik"] - 1)
        satirlar += [kutusuz, kutulu]
    return satirlar


def kayma_etkisi(tasarim, bosluklar, f_x_max: float, yuva: str | None = None) -> list[dict]:
    """Kutu yuvada ±δ kayarsa trim açısı değişimi ve duvara çarpmanın gövdeye etkisi.

    f_x_max: kutunun yuvada gördüğü en büyük gövdeye dik özgül kuvvet [m/s^2] (manevralardan).
    Kutu karşı duvara 2δ yol alarak çarpar: Δv = √(2·f·2δ), açısal itme m_k Δv z_k.
    """
    taban = tasarim.govde(kutulu=True, yuva=yuva)
    p = tasarim.model(kutulu=True, yuva=yuva)
    m_k = tasarim.d("yuk.kutu.kutle")
    z_k = tasarim.kutu_merkez_z(yuva)
    J_O = p.I_yy + p.m_b * p.l**2
    satirlar = []
    for delta in bosluklar:
        g = tasarim.govde(kutulu=True, yuva=yuva, kayma=(delta, 0.0))
        dv = math.sqrt(2 * f_x_max * 2 * delta)
        satirlar.append(
            {
                "delta": delta,
                "dx_c": g.km[0] - taban.km[0],
                "dtrim": math.degrees(denge_acisi(g.km) - denge_acisi(taban.km)),
                "carpma_dv": dv,
                "dthetad": m_k * dv * z_k / J_O,
            }
        )
    return satirlar


def batarya_taramasi(tasarim, z_listesi) -> dict:
    """Batarya yüksekliği değişince (KM yüksekliği) kutuplar, tork ve düşme süresi."""
    sonuc = {k: [] for k in ("z", "l", "p_serbest", "p_kilitli", "kok_g_l", "tau_statik", "tau_tutma", "t_dusme")}
    for z in z_listesi:
        s = durum_ozeti(tasarim, "", kutulu=True, z_batarya=z)
        sonuc["z"].append(z)
        for k in ("l", "p_serbest", "p_kilitli", "kok_g_l", "tau_statik", "tau_tutma", "t_dusme"):
            sonuc[k].append(s[k])
    return {k: np.asarray(v, float) for k, v in sonuc.items()}


def kutu_yuksekligi_taramasi(tasarim, z_listesi, manevralar: dict) -> dict:
    """Kutu merkezinin yüksekliğine göre KM, kutup ve yuvadaki görünür eğim açısı α.

    manevralar: ad → doğrusal referans yörüngesi (simulasyon.referans_*); kutunun gövde
    dinamiğine etkisi küçük olduğundan yörüngeler sabit tutulur.
    """
    g_ivme = tasarim.d("sabit.g")
    x_k = tasarim.d("yuk.yuva.x")
    sonuc = {"z": np.asarray(z_listesi, float), "l": [], "p_serbest": [], "tau_statik": []}
    sonuc |= {f"alfa_{ad}": [] for ad in manevralar} | {f"fx_{ad}": [] for ad in manevralar}
    th0 = math.radians(tasarim.d("sartname.toparlanma_acisi"))
    for z in z_listesi:
        p = tasarim.model(kutulu=True, z_kutu=z)
        sonuc["l"].append(p.l)
        sonuc["p_serbest"].append(model.kararsiz_kutup(p))
        sonuc["tau_statik"].append(p.m_b * p.g * p.l * math.sin(th0))
        for ad, y in manevralar.items():
            fx, fz = ozgul_kuvvet(y["xdd"], y["theta"], y["theta_d"], y["theta_dd"], x_k, z, g_ivme)
            sonuc[f"alfa_{ad}"].append(math.degrees(np.max(np.abs(np.arctan2(fx, fz)))))
            sonuc[f"fx_{ad}"].append(float(np.max(np.abs(fx))))
    return {k: np.asarray(v, float) for k, v in sonuc.items()}
