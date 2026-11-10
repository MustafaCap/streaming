//! Uygulama sürümü (pencere başlığında ve logda görünür).
pub const SURUM: &str = env!("CARGO_PKG_VERSION");
/// Derlemenin kimliği (CI'da commit'in ilk 8 hanesi, yerelde "yerel").
pub const DERLEME: &str = env!("RIZEON_DERLEME");
pub const UYGULAMA_ADI: &str = "RizeOn";
