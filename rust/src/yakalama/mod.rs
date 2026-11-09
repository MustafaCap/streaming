//! Görüntü kaynakları: ekran (DXGI, yedeği GDI) ve kamera (Media Foundation).
pub mod ekran;
#[cfg(windows)]
pub mod kamera;
#[cfg(windows)]
pub mod pencere;
#[cfg(windows)]
mod dxgi;
#[cfg(windows)]
mod gdi;

/// Monitör: sanal masaüstündeki yeri ve boyutu.
#[derive(Clone, Debug, PartialEq)]
pub struct Monitor {
    pub ad: String,
    pub sol: i32,
    pub ust: i32,
    pub w: u32,
    pub h: u32,
}

/// Bağlı monitörler, numara sırasıyla ("Göster" menüsü için).
pub fn monitorler() -> Vec<Monitor> {
    #[cfg(windows)]
    {
        dxgi::monitorler()
    }
    #[cfg(not(windows))]
    {
        vec![]
    }
}
