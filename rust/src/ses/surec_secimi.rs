//! Hangi uygulamaların sesi ayrı ayrı yakalanacak (saf mantık, testli).

use std::collections::{HashMap, HashSet};

/// pid'in kendisi ve bütün üst süreçleri (döngüye karşı en fazla 64 adım).
pub fn atalar(mut pid: u32, tablo: &HashMap<u32, (u32, String)>) -> Vec<u32> {
    let mut zincir = vec![];
    let mut gorulen = HashSet::new();
    while pid != 0 && tablo.contains_key(&pid) && !gorulen.contains(&pid) && zincir.len() < 64 {
        zincir.push(pid);
        gorulen.insert(pid);
        pid = tablo[&pid].0;
    }
    zincir
}

/// Atılanlar: hariç listesindeki uygulamalar ve alt süreçleri, kendi sürecimiz ve alt süreçleri,
/// kendimizin ya da hariç tutulanın ÜST süreçleri (explorer.exe ağacını yakalarsak biz de içinde oluruz).
/// Üst süreci zaten listedeyse ayrıca yakalanmaz.
pub fn yakalanacak_surecler(oturum: &HashSet<u32>, haric_adlar: &[String], kendi: u32, tablo: &HashMap<u32, (u32, String)>) -> HashSet<u32> {
    let haric: HashSet<String> = haric_adlar.iter().map(|a| a.to_lowercase()).collect();
    let mut yasakli: HashSet<u32> = atalar(kendi, tablo).into_iter().collect();
    for (pid, (_, ad)) in tablo {
        if haric.contains(ad) {
            yasakli.extend(atalar(*pid, tablo));
        }
    }
    let ad = |p: &u32| tablo.get(p).map(|(_, a)| a.as_str()).unwrap_or("");
    let mut adaylar = HashSet::new();
    for pid in oturum {
        let mut zincir = atalar(*pid, tablo);
        if zincir.is_empty() {
            zincir.push(*pid);
        }
        if yasakli.contains(pid) || zincir.contains(&kendi) || zincir.iter().any(|p| haric.contains(ad(p))) {
            continue;
        }
        adaylar.insert(*pid);
    }
    // atalar() tabloda olmayan pid için boş döner (kısa ömürlü süreç, sistem oturumu): skip(1) taşmaz
    adaylar.iter().filter(|p| !atalar(**p, tablo).iter().skip(1).any(|a| adaylar.contains(a))).copied().collect()
}

#[cfg(test)]
mod testler {
    use super::*;
    #[test]
    fn zoom_ve_kendimiz_haric() {
        let t: HashMap<u32, (u32, String)> = [
            (1, (0, "explorer.exe")),
            (10, (1, "rizeon.exe")),
            (11, (10, "ffmpeg.exe")),
            (20, (1, "zoom.exe")),
            (21, (20, "zoomaudio.exe")),
            (30, (1, "msedge.exe")),
            (31, (30, "msedge.exe")),
            (40, (1, "spotify.exe")),
        ]
        .into_iter()
        .map(|(p, (e, a))| (p, (e, a.to_string())))
        .collect();
        let oturum: HashSet<u32> = [1, 11, 21, 30, 31, 40].into_iter().collect();
        let s = yakalanacak_surecler(&oturum, &["Zoom.exe".into()], 10, &t);
        assert_eq!(s, [30, 40].into_iter().collect());
    }

    /// Ses oturumu olan ama süreç listesinde bulunmayan pid (ör. 0 ya da yeni kapanmış süreç)
    /// eskiden dilimi taşırıp ses motorunu çökertiyordu.
    #[test]
    fn tabloda_olmayan_surec_cokertmez() {
        let t: HashMap<u32, (u32, String)> = [(1, (0, "explorer.exe".to_string())), (40, (1, "spotify.exe".to_string()))].into_iter().collect();
        let oturum: HashSet<u32> = [0, 40, 999].into_iter().collect();
        let s = yakalanacak_surecler(&oturum, &[], 10, &t);
        assert!(s.contains(&40) && s.contains(&999));
    }
}
