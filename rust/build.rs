// Windows exe'sine simge ve sürüm bilgisi gömer (Görev Yöneticisi ve Özellikler penceresinde görünür).
fn main() {
    // Kilit dosyaları gibi "bu derleme" bilgisi gereken yerler için (CI'da commit kimliği).
    let derleme = std::env::var("GITHUB_SHA").map(|s| s.chars().take(8).collect::<String>()).unwrap_or_else(|_| "yerel".into());
    println!("cargo:rustc-env=RIZEON_DERLEME={derleme}");
    println!("cargo:rerun-if-env-changed=GITHUB_SHA");
    println!("cargo:rerun-if-changed=../kurulum/uygulama.ico");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        let mut r = winresource::WindowsResource::new();
        r.set_icon("../kurulum/uygulama.ico")
            .set("ProductName", "RizeOn")
            .set("FileDescription", "RizeOn")
            .set("CompanyName", "MustafaCap")
            .set("LegalCopyright", "GPLv3 · github.com/MustafaCap/streaming");
        if let Err(e) = r.compile() {
            println!("cargo:warning=Simge gömülemedi: {e}");
        }
    }
}
