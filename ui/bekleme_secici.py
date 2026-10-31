"""Bekleme ekranı için resim ya da kısa video seçme (ana pencere ve Ayarlar kullanır)."""

import logging

from PySide6.QtWidgets import QFileDialog, QMessageBox

log = logging.getLogger(__name__)

FILTRE = ("Resim ya da video (*.png *.jpg *.jpeg *.bmp *.webp *.mp4 *.webm *.avi *.mov *.mkv *.gif *.wmv *.m4v);;"
          "Resimler (*.png *.jpg *.jpeg *.bmp *.webp);;Videolar (*.mp4 *.webm *.avi *.mov *.mkv *.gif *.wmv *.m4v)")


def dosya_sec(ebeveyn, baslangic: str = "") -> str:
    """Seçilen dosyanın kullanılacak yolu ('' = vazgeçildi). Videolar uygulama klasörüne kopyalanır."""
    yol, _ = QFileDialog.getOpenFileName(ebeveyn, "Bekleme ekranı: resim ya da kısa video", baslangic, FILTRE)
    if not yol:
        return ""
    from core.standby import uygulamaya_kopyala, video_mu
    if video_mu(yol):
        try:
            return uygulamaya_kopyala(yol)
        except OSError as e:
            log.warning("Video kopyalanamadı: %s", e)
            QMessageBox.warning(ebeveyn, "Bekleme ekranı", f"Video kopyalanamadı:\n{e}")
            return ""
    return yol


def uygula(ayarlar, hat, yol: str) -> None:
    ayarlar.ayarla("standby_image", yol)
    if hat is not None:
        hat.bekleme_gorseli = yol
