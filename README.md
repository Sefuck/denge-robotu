# Denge robotu: Modül A ve E (Kontrol ve Otomasyon)

YTÜ EEF ÇDTP 2026-2027 Güz, *İki Tekerlekli Ev İçi Hasta Destek Robotu*.
Sefa Nurali Uçak (23015008): robot dinamiği, durum kestirimi, denge/hareket kontrolü, yükle kararlılık.

## 3. hafta teslimatı

**[docs/hafta03_model_tork_km.md](docs/hafta03_model_tork_km.md)**: ters sarkaç matematiksel modeli,
motor tork/devir hesapları ve ilaç kutusu yuvasının kütle merkezi analizi.

Motor, teker ve batarya henüz alınmadı. Bütün fiziksel parametreler **tahminidir** ve tek dosyada,
kaynaklarıyla birlikte tutulur: [`parametreler.toml`](parametreler.toml).

## Kurulum

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Kullanım

```
.venv/bin/python -m denge              # şekilleri ve dokümanı parametre dosyasından yeniden üretir (+ test özeti)
.venv/bin/python -m pytest -q          # doğrulama testleri
.venv/bin/python -m denge.motor --gerilim 12 --bosta-devir 300 --durma-torku 8 \
    --durma-akimi 3 --bosta-akim 0.2 --reduksiyon 30 --ppr 11   # aday motoru gereksinimlere göre sınar
```

Parça gelince: `parametreler.toml` içindeki değeri ölçülmüş değerle değiştir, `durum = "ölçülmüş"` yap,
`kaynak` alanına ölçüm yöntemini yaz, sonra `python -m denge` ile dokümanı yeniden üret. Doküman
şablondan (`docs/sablon/hafta03.md`) üretilir. Sayılar değişince metindeki yorumları da gözden geçir.

## Yapı

| Dosya | İçerik |
|---|---|
| `parametreler.toml` | Bütün parametreler: değer, birim, durum (tahmini / şartname / öneri / sabit), kaynak, aralık |
| `denge/model.py` | Lagrange–d'Alembert türetimi (sympy), doğrusal olmayan model, doğrusallaştırma, A-B-C-D, transfer fonksiyonları, ayrıklaştırma |
| `denge/simulasyon.py` | ±10° açık çevrim düşme (serbest/kilitli teker), düz çıkışla referans manevralar, ters dinamik |
| `denge/motor.py` | Devir, toparlanma torku, çekiş, enkoder; aday motor değerlendirme aracı |
| `denge/kutle_merkezi.py` | KM, atalet tensörü, yere değme açısı, yuvadaki özgül kuvvet |
| `denge/yuva_analizi.py` | Kutulu/kutusuz KM, kutu kayması, KM yüksekliği taraması, yuva seçenekleri |
| `denge/sekiller.py`, `denge/rapor.py` | Şekiller ve doküman üretimi |
| `tests/` | Model, simülasyon, birim (pint), duyarlılık ve parametre dosyası testleri |

Kaynak PDF'ler (`kaynaklar/`: danışman iş planı, şartname TR/EN v14, tanıtım sunumu) yerelde tutulur, depoya eklenmez.
