"""3D ikizin görüntü çıktıları: sabit kameralı MP4 (yan + çapraz yan yana), sunum karesi (PNG).

Kamera robotu izlemez; her senaryo için yörüngenin tamamını kadraja alacak biçimde bir kez yerleştirilir.
Video, simülasyon sırasında kaydedilen gövde ve kutu konumlarından sonradan çizilir (ffmpeg, H.264).
"""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import numpy as np

YAN, CAPRAZ = "yan", "capraz"
KAMERA_ADLARI = {YAN: "yan görünüş", CAPRAZ: "çapraz görünüş"}


def _font(boyut: int):
    from matplotlib import font_manager
    from PIL import ImageFont

    return ImageFont.truetype(font_manager.findfont("DejaVu Sans"), boyut)


def _sayi(x, n=2) -> str:
    return f"{x:.{n}f}".replace("-", "−").replace(".", ",")


def kamera(gorunus: str, kareler) -> "mujoco.MjvCamera":
    """Yörüngenin (X, Y) sınırlarına göre sabit serbest kamera."""
    import mujoco

    xy = np.array([q[:2] for _, q, _ in kareler]) if kareler else np.zeros((1, 2))
    lo, hi = xy.min(axis=0) - 0.08, xy.max(axis=0) + 0.08
    merkez = (lo + hi) / 2
    acilim = float(max(hi[0] - lo[0], hi[1] - lo[1], 0.45))
    c = mujoco.MjvCamera()
    c.type = mujoco.mjtCamera.mjCAMERA_FREE
    c.lookat[:] = (merkez[0], merkez[1], 0.11)
    if gorunus == YAN:
        c.azimuth, c.elevation = 90.0, -5.0
        c.distance = 0.22 + 0.80 * acilim
    else:
        c.azimuth, c.elevation = 135.0, -22.0
        c.distance = 0.28 + 0.78 * acilim
    return c


def _ust_bilgi(img, baslik: str, alt: str, sag: str, sonuc: str | None):
    from PIL import ImageDraw

    dr = ImageDraw.Draw(img, "RGBA")
    W, H = img.size
    dr.rectangle([0, 0, W, 64], fill=(255, 255, 255, 215))
    dr.text((18, 8), baslik, font=_font(24), fill=(11, 11, 11))
    dr.text((18, 38), alt, font=_font(17), fill=(82, 81, 78))
    dr.text((W - 18, 22), sag, font=_font(17), fill=(82, 81, 78), anchor="ra")
    if sonuc:
        renk = (27, 140, 90) if sonuc == "GEÇTİ" else (200, 40, 30)
        kutu = dr.textbbox((0, 0), sonuc, font=_font(34))
        w, h = kutu[2] - kutu[0] + 30, kutu[3] - kutu[1] + 22
        dr.rounded_rectangle([W - w - 18, H - h - 18, W - 18, H - 18], radius=10, fill=renk + (230,))
        dr.text((W - w / 2 - 18, H - h / 2 - 18), sonuc, font=_font(34), fill=(255, 255, 255), anchor="mm")


def mp4_yaz(yol: Path, m, kareler, baslik: str, alt_baslik: str, sonuc: str | None = None, hiz: float = 1.0,
            fps: int = 30, genislik: int = 960, yukseklik: int = 540, crf: int = 22, t_son: float | None = None) -> int:
    """Yan ve çapraz görünüş yan yana (2·genislik × yukseklik). hiz < 1 ağır çekimdir. Dönen: kare sayısı."""
    import mujoco
    from PIL import Image, ImageDraw

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg bulunamadı (macOS: brew install ffmpeg)")
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    d = mujoco.MjData(m)
    r = mujoco.Renderer(m, yukseklik, genislik)
    kameralar = {g: kamera(g, kareler) for g in (YAN, CAPRAZ)}
    t_kayit = np.array([tk for tk, _, _ in kareler])
    t_son = t_kayit[-1] if t_son is None else min(t_son, t_kayit[-1])
    zamanlar = np.arange(0.0, t_son + 1e-9, hiz / fps)
    W, H = 2 * genislik, yukseklik
    p = subprocess.Popen([ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
                          "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf), "-preset", "medium",
                          "-movflags", "+faststart", str(yol)], stdin=subprocess.PIPE)
    hiz_metni = "" if hiz == 1.0 else f" · {_sayi(hiz, 2).rstrip('0').rstrip(',')}× yavaş"
    son_kare = None
    for tz in zamanlar:
        j = min(int(np.searchsorted(t_kayit, tz)), len(kareler) - 1)
        _, q, ek = kareler[j]
        d.qpos[:] = q
        mujoco.mj_forward(m, d)
        parcalar = []
        for g in (YAN, CAPRAZ):
            r.update_scene(d, camera=kameralar[g])
            parca = Image.fromarray(r.render())
            ImageDraw.Draw(parca).text((14, yukseklik - 32), KAMERA_ADLARI[g], font=_font(16), fill=(60, 60, 60))
            parcalar.append(parca)
        img = Image.new("RGB", (W, H))
        img.paste(parcalar[0], (0, 0))
        img.paste(parcalar[1], (genislik, 0))
        bilgi = f"t = {_sayi(tz, 2)} s   θ = {_sayi(math.degrees(ek['theta']), 1)}°   x = {_sayi(100 * ek['x'], 1)} cm   ψ = {_sayi(math.degrees(ek['psi']), 0)}°"
        son_kare = img.copy()
        _ust_bilgi(img, baslik, alt_baslik + hiz_metni, bilgi, None)
        p.stdin.write(img.tobytes())
    # Sonuç kartı: son kare 1,5 s sonuçla birlikte bekletilir
    if son_kare is not None and sonuc:
        _ust_bilgi(son_kare, baslik, alt_baslik + hiz_metni, bilgi, sonuc)
        for _ in range(int(1.5 * fps)):
            p.stdin.write(son_kare.tobytes())
    p.stdin.close()
    p.wait()
    r.close()
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg hata kodu {p.returncode}")
    return len(zamanlar)


def kare_png(yol: Path, m, q, gorunus: str = CAPRAZ, genislik: int = 1600, yukseklik: int = 900, uzaklik: float | None = None) -> None:
    """Tek kare (sunum ve belge için)."""
    import mujoco
    from PIL import Image

    d = mujoco.MjData(m)
    d.qpos[:] = q
    mujoco.mj_forward(m, d)
    r = mujoco.Renderer(m, yukseklik, genislik)
    c = mujoco.MjvCamera()
    c.type = mujoco.mjtCamera.mjCAMERA_FREE
    c.lookat[:] = (q[0], q[1], 0.11)
    c.azimuth, c.elevation = (135.0, -20.0) if gorunus == CAPRAZ else (90.0, -6.0)
    c.distance = uzaklik or 0.62
    r.update_scene(d, camera=c)
    Image.fromarray(r.render()).save(yol)
    r.close()
