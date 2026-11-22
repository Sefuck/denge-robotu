# Denge robotu: Modül A ve E (Kontrol ve Otomasyon)

## Buradan başla

1. **Toplantı özeti (1 sayfa):** [docs/hafta03_toplanti_ozeti.md](docs/hafta03_toplanti_ozeti.md)
2. **Tam belge (hesaplar, şekiller, kaynaklar):** [docs/hafta03_model_tork_km.md](docs/hafta03_model_tork_km.md)
3. **Kod ve parametreler:** [`parametreler.toml`](parametreler.toml), [`denge/`](denge/), [`tests/`](tests/) (aşağıda)

| Hafta | Danışman teslimatı | Özet | Tam belge | Durum |
|---|---|---|---|---|
| 3 | Ters sarkaç matematiksel modeli, motor tork/hız hesapları ve ilaç kutusu yuvasının kütle merkezi analizi dokümanı | [Özet](docs/hafta03_toplanti_ozeti.md) | [Tam belge](docs/hafta03_model_tork_km.md) | Hazır (19 Ekim 2026 toplantısı); step motor seçeneği §10, satın alınan 1000 RPM motor §11, kapalı çevrim simülasyon (dijital ikiz) §12'de; parametreler ölçülmedi |

---

YTÜ EEF ÇDTP 2026-2027 Güz, *İki Tekerlekli Ev İçi Hasta Destek Robotu*.
Sefa Nurali Uçak (23015008): robot dinamiği, durum kestirimi, denge/hareket kontrolü, yükle kararlılık.

Teker ve batarya henüz alınmadı; motorlar (JGB37-520 12 V 1000 RPM) alındı ama ölçülmedi. Kontrolcü ve kestirici yalnız simülasyonda (§12) çalıştı. Hiçbir fiziksel parametre ölçülmedi. Bütün parametreler tek dosyada,
kaynaklarıyla birlikte tutulur: [`parametreler.toml`](parametreler.toml). Durumlar: `ön liste` (ön malzeme listesi,
cdtp-robot.netlify.app'teki referans malzeme listesinden derlendi; Mete'nin seçimiyle kesinleşecek), `doğrulanamadı`
(rcdrone motor referans tablosu), `tahmini` (listede olmayan değerler).

## Kurulum

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

PDF üretimi için ayrıca Google Chrome gerekir (pandoc, `pypandoc_binary` ile sanal ortama kurulur).

## Kullanım

```
.venv/bin/python -m denge              # şekilleri, tam belgeyi ve özeti parametre dosyasından yeniden üretir (+ simülasyon matrisi ve test özeti, ≈ 3 dk)
.venv/bin/python -m denge --pdf        # ayrıca docs/pdf/ altına iki PDF üretir (depoya eklenmez)
.venv/bin/python -m pytest -q          # doğrulama testleri
.venv/bin/python -m denge.motor --dosyadaki-aday --oran-taramasi   # ön listedeki aday motor (JGB37-520 530 RPM) + oran taraması
.venv/bin/python -m denge.motor --satin-alinan --yan-yana   # satın alınan 1000 RPM motor: boş/dolu pil, 530/333 ile yan yana
.venv/bin/python -m denge.step         # step motor (17HS4401 + DRV8825): tork-devir noktaları ve adım kaçırma payı
.venv/bin/python -m denge.ikiz         # dijital ikiz: şartname senaryoları × kontrolcü × kestirici × kutu × pil × motor; özet + docs/simulasyon/sonuclar.csv
.venv/bin/python -m denge.ikiz --senaryo O1-4+ --motor 333 --pil bos --kontrolcu pid --grafik g.png --gif a.gif   # tek senaryo
.venv/bin/python -m denge.ikiz --lqr-tasarla   # parametreler değişince LQI kazançlarını Q, R'den yeniden hesaplar (kontrol.lqr.K'ye yazılır)
.venv/bin/python -m denge.ikiz --pay           # Ö1-4'ün geçtiği en büyük başlangıç eğimi, her motor ve pil için
.venv/bin/python -m denge.motor --gerilim 12 --bosta-devir 300 --durma-torku 8 \
    --durma-akimi 3 --bosta-akim 0.2 --reduksiyon 30 --ppr 11   # başka bir adayı veri sayfası değerleriyle sınar
```

Satın alınan motor ölçülünce değerler `motor_olcum` alanlarına girilir (boş liste = ölçülmedi); `python -m denge` §11'deki kararı ölçümle yeniden üretir. Rotor ataleti (`ikiz.rotor_ataleti_motor`), dişli boşluğu (`ikiz.reduktor_boslugu`) ve pil iç direnci (`ikiz.pil_ic_direnci`) ölçülünce §12'deki simülasyon ve motor kararı da yeniden üretilir; fiziksel parametreler değişirse önce `python -m denge.ikiz --lqr-tasarla` ile kazançlar yenilenir (test bunu denetler).

Motor tipi `parametreler.toml` içindeki `tahrik.tip` ile seçilir (`dc` / `step`). 17HS4401'in pull-out eğrisi ölçülünce `step_egri.olcum` alanları doldurulur; o zaman kardeş motorlardan türetilen geçici eğri yerine ölçüm kullanılır.

Parça gelince: `parametreler.toml` içindeki değeri ölçülmüş değerle değiştir, `durum = "ölçülmüş"` yap,
`kaynak` alanına ölçüm yöntemini yaz, sonra `python -m denge` ile belgeleri yeniden üret. Belgeler
şablonlardan (`docs/sablon/`) üretilir; çıktıları doğrudan düzenleme. Sayılar değişince metindeki yorumları da gözden geçir.

Her hafta: yeni şablonları `docs/sablon/` altına ekle, yukarıdaki hafta tablosuna bir satır ekle.

## Yapı

| Dosya | İçerik |
|---|---|
| `parametreler.toml` | Bütün parametreler: değer, birim, durum (tahmini / ön liste / doğrulanamadı / şartname / öneri / sabit), kaynak, aralık |
| `denge/model.py` | Lagrange–d'Alembert türetimi (sympy), doğrusal olmayan model, doğrusallaştırma, A-B-C-D, transfer fonksiyonları, ayrıklaştırma; ivme girişli (step) model |
| `denge/simulasyon.py` | ±10° açık çevrim düşme (serbest/kilitli teker, detent), düz çıkışla referans manevralar, ters dinamik, ivme girişli yörünge |
| `denge/motor.py` | Devir, toparlanma torku, çekiş, enkoder; aday motor değerlendirme ve oran taraması |
| `denge/step.py` | Step motor seçeneği: geçici pull-out eğrisi, adım kaçırma payı, adım frekansı, güç ve pil süresi |
| `denge/satin_alinan.py` | Satın alınan motor: gereksinime karşı sınama, karar, teker / ek redüksiyon / kütle çözümleri |
| `denge/kutle_merkezi.py` | KM, atalet tensörü, yere değme açısı, yuvadaki özgül kuvvet |
| `denge/yuva_analizi.py` | Kutulu/kutusuz KM, kutu kayması, KM yüksekliği taraması, yuva seçenekleri |
| `denge/ikiz/` | Dijital ikiz (§12): `fizik` (7 serbestlikli model, teker kayması, dişli boşluğu, motor, pil), `sensorler` (MPU6050, enkoder), `kestirim` (Kalman, tamamlayıcı; ESP32'ye taşınabilir), `kontrol` (PID, LQI, çıkış katı; ESP32'ye taşınabilir), `senaryolar` (Ö1-1 … Ö2, geçti/kaldı, düşme nedeni), `toplu`, `cizim` (grafik, GIF), `rapor_bolumu` |
| `docs/simulasyon/sonuclar.csv` | Simülasyonun her koşusu ve alt testi: sonuç, metrikler, kalma nedeni (üretilir) |
| `denge/sekiller.py`, `denge/rapor.py`, `denge/pdf.py` | Şekiller, belge ve özet üretimi, PDF çevirisi |
| `docs/sablon/` | Tam belge ve özet şablonları, PDF stilleri |
| `tests/` | Model, simülasyon, birim (pint), duyarlılık, step motor, satın alınan motor, dijital ikiz, parametre dosyası ve ifade testleri |

Kaynak PDF'ler (`kaynaklar/`: danışman iş planı, şartname TR/EN v14, tanıtım sunumu) yerelde tutulur, depoya eklenmez.
