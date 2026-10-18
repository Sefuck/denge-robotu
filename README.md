# Denge robotu: Modül A ve E (Kontrol ve Otomasyon)

## Buradan başla

1. **Toplantı özeti (1 sayfa):** [docs/hafta03_toplanti_ozeti.md](docs/hafta03_toplanti_ozeti.md)
2. **Tam belge (hesaplar, şekiller, kaynaklar):** [docs/hafta03_model_tork_km.md](docs/hafta03_model_tork_km.md)
3. **Kod ve parametreler:** [`parametreler.toml`](parametreler.toml), [`denge/`](denge/), [`tests/`](tests/) (aşağıda)

| Hafta | Danışman teslimatı | Özet | Tam belge | Durum |
|---|---|---|---|---|
| 3 | Ters sarkaç matematiksel modeli, motor tork/hız hesapları ve ilaç kutusu yuvasının kütle merkezi analizi dokümanı | [Özet](docs/hafta03_toplanti_ozeti.md) | [Tam belge](docs/hafta03_model_tork_km.md) | Hazır (19 Ekim 2026 toplantısı); parametreler ölçülmedi |

---

YTÜ EEF ÇDTP 2026-2027 Güz, *İki Tekerlekli Ev İçi Hasta Destek Robotu*.
Sefa Nurali Uçak (23015008): robot dinamiği, durum kestirimi, denge/hareket kontrolü, yükle kararlılık.

Motor, teker ve batarya henüz alınmadı; hiçbir fiziksel parametre ölçülmedi. Bütün parametreler tek dosyada,
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
.venv/bin/python -m denge              # şekilleri, tam belgeyi ve özeti parametre dosyasından yeniden üretir (+ test özeti)
.venv/bin/python -m denge --pdf        # ayrıca docs/pdf/ altına iki PDF üretir (depoya eklenmez)
.venv/bin/python -m pytest -q          # doğrulama testleri
.venv/bin/python -m denge.motor --dosyadaki-aday --oran-taramasi   # ön listedeki aday motor (JGB37-520 530 RPM) + oran taraması
.venv/bin/python -m denge.motor --gerilim 12 --bosta-devir 300 --durma-torku 8 \
    --durma-akimi 3 --bosta-akim 0.2 --reduksiyon 30 --ppr 11   # başka bir adayı veri sayfası değerleriyle sınar
```

Parça gelince: `parametreler.toml` içindeki değeri ölçülmüş değerle değiştir, `durum = "ölçülmüş"` yap,
`kaynak` alanına ölçüm yöntemini yaz, sonra `python -m denge` ile belgeleri yeniden üret. Belgeler
şablonlardan (`docs/sablon/`) üretilir; çıktıları doğrudan düzenleme. Sayılar değişince metindeki yorumları da gözden geçir.

Her hafta: yeni şablonları `docs/sablon/` altına ekle, yukarıdaki hafta tablosuna bir satır ekle.

## Yapı

| Dosya | İçerik |
|---|---|
| `parametreler.toml` | Bütün parametreler: değer, birim, durum (tahmini / ön liste / doğrulanamadı / şartname / öneri / sabit), kaynak, aralık |
| `denge/model.py` | Lagrange–d'Alembert türetimi (sympy), doğrusal olmayan model, doğrusallaştırma, A-B-C-D, transfer fonksiyonları, ayrıklaştırma |
| `denge/simulasyon.py` | ±10° açık çevrim düşme (serbest/kilitli teker), düz çıkışla referans manevralar, ters dinamik |
| `denge/motor.py` | Devir, toparlanma torku, çekiş, enkoder; aday motor değerlendirme ve oran taraması |
| `denge/kutle_merkezi.py` | KM, atalet tensörü, yere değme açısı, yuvadaki özgül kuvvet |
| `denge/yuva_analizi.py` | Kutulu/kutusuz KM, kutu kayması, KM yüksekliği taraması, yuva seçenekleri |
| `denge/sekiller.py`, `denge/rapor.py`, `denge/pdf.py` | Şekiller, belge ve özet üretimi, PDF çevirisi |
| `docs/sablon/` | Tam belge ve özet şablonları, PDF stilleri |
| `tests/` | Model, simülasyon, birim (pint), duyarlılık, parametre dosyası ve ifade testleri |

Kaynak PDF'ler (`kaynaklar/`: danışman iş planı, şartname TR/EN v14, tanıtım sunumu) yerelde tutulur, depoya eklenmez.
