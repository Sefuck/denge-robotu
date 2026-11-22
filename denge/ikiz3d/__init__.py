"""3D dijital ikiz (MuJoCo), belge §12.11.

Modüller:
    mjcf   : parametreler.toml → MJCF; kütle özellikleri
    kosucu : MuJoCo döngüsünde 2D ikizin motor, sensör, kestirici ve kontrolcü kodu; senaryolar ve değerlendirme
    video  : sabit kameralı MP4 kaydı ve sunum karesi
    karsilastirma : 2D ve 3D sonuçları yan yana, belge yer tutucuları

Komut satırı: python -m denge.ikiz3d --help (canlı izleme macOS'ta mjpython ile)
"""
