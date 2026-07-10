import os
import shutil
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

# Şarkıların ve kapakların kaydedileceği klasör yolu
MUSIC_DIR = os.path.expanduser("~/musicapp/musicfiles")

# Klasör yoksa otomatik oluşturulur
os.makedirs(MUSIC_DIR, exist_ok=True)

# İndirme için link modeli
class LinkModel(BaseModel):
    url: str

# Şarkı adı ve başlık güncelleme modeli
class GuncellemeModel(BaseModel):
    eski_sarki_adi: str  # Örn: "Metallica - Master.mp3"
    yeni_baslik: str     # Örn: "Metallica - Master of Puppets" (Uzantısız sade başlık)

# Silme işlemi için model
class SilmeModel(BaseModel):
    sarki_adi: str  # Örn: "Metallica - One.mp3"

@app.post("/indir")
def youtube_indir(data: LinkModel):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{MUSIC_DIR}/%(title)s.%(ext)s',
        'writethumbnail': True, 
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }
        ],
        'noplaylist': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([data.url])
        return {"durum": "basarili", "mesaj": "Sarki ve kapak resmi basariyla indirildi!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indirme hatasi: {str(e)}")

@app.get("/sarkilar")
def sarkilari_listele():
    try:
        dosyalar = os.listdir(MUSIC_DIR)
        mp3_dosyalari = [f for f in dosyalar if f.endswith('.mp3')]
        
        havuz = []
        for mp3 in mp3_dosyalari:
            sarki_adi = mp3.replace('.mp3', '')
            
            kapak_adi = None
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                if f"{sarki_adi}{ext}" in dosyalar:
                    kapak_adi = f"{sarki_adi}{ext}"
                    break
            
            havuz.append({
                "sarki_adi": mp3,
                "baslik": sarki_adi,
                "kapak_url": f"/kapak/{kapak_adi}" if kapak_adi else None
            })
            
        return {"sarkilar": sorted(havuz, key=lambda x: x['baslik'])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/dinle/{sarki_adi}")
def sarki_dinle(sarki_adi: str):
    sarki_yolu = os.path.join(MUSIC_DIR, sarki_adi)
    if os.path.exists(sarki_yolu):
        return FileResponse(sarki_yolu, media_type="audio/mpeg")
    raise HTTPException(status_code=404, detail="Sarki bulunamadi.")

@app.get("/kapak/{resim_adi}")
def kapak_resmi_getir(resim_adi: str):
    resim_yolu = os.path.join(MUSIC_DIR, resim_adi)
    if os.path.exists(resim_yolu):
        media_type = "image/jpeg"
        if resim_adi.endswith('.png'):
            media_type = "image/png"
        elif resim_adi.endswith('.webp'):
            media_type = "image/webp"
            
        return FileResponse(resim_yolu, media_type=media_type)
    raise HTTPException(status_code=404, detail="Kapak resmi bulunamadi.")

@app.get("/ara")
def youtube_ara(isim: str):
    if not isim:
        raise HTTPException(status_code=400, detail="Arama metni bos olamaz.")
        
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'extract_flat': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            arama_sonucu = ydl.extract_info(f"ytsearch5:{isim}", download=False)
            
        sonuclar = []
        if 'entries' in arama_sonucu:
            for entry in arama_sonucu['entries']:
                sonuclar.append({
                    "baslik": entry.get("title"),
                    "url": f"https://www.youtube.com/watch?v={entry.get('id')}"
                })
        return {"sonuclar": sonuclar}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Arama hatasi: {str(e)}")

@app.post("/guncelle/bilgi")
def sarki_bilgi_guncelle(data: GuncellemeModel):
    if not data.eski_sarki_adi.endswith('.mp3'):
        raise HTTPException(status_code=400, detail="Eski sarki adi .mp3 ile bitmelidir.")
        
    eski_sarki_yolu = os.path.join(MUSIC_DIR, data.eski_sarki_adi)
    if not os.path.exists(eski_sarki_yolu):
        raise HTTPException(status_code=404, detail="Guncellenmek istenen sarki dosyasi bulunamadi.")
        
    eski_temiz_ad = data.eski_sarki_adi.replace('.mp3', '')
    yeni_temiz_ad = data.yeni_baslik.strip()
    yeni_sarki_adi = f"{yeni_temiz_ad}.mp3"
    yeni_sarki_yolu = os.path.join(MUSIC_DIR, yeni_sarki_adi)
    
    if os.path.exists(yeni_sarki_yolu) and data.eski_sarki_adi != yeni_sarki_adi:
        raise HTTPException(status_code=400, detail="Bu yeni isimde bir sarki zaten mevcut.")
        
    try:
        os.rename(eski_sarki_yolu, yeni_sarki_yolu)
        
        dosyalar = os.listdir(MUSIC_DIR)
        guncellenen_kapak = None
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            eski_kapak_adi = f"{eski_temiz_ad}{ext}"
            if eski_kapak_adi in dosyalar:
                eski_kapak_yolu = os.path.join(MUSIC_DIR, eski_kapak_adi)
                yeni_kapak_adi = f"{yeni_temiz_ad}{ext}"
                yeni_kapak_yolu = os.path.join(MUSIC_DIR, yeni_kapak_adi)
                os.rename(eski_kapak_yolu, yeni_kapak_yolu)
                guncellenen_kapak = yeni_kapak_adi
                break
                
        return {
            "durum": "basarili", 
            "mesaj": "Sarki ismi ve kapak resmi basariyla guncellendi.",
            "yeni_sarki_adi": yeni_sarki_adi,
            "yeni_kapak_url": f"/kapak/{guncellenen_kapak}" if guncellenen_kapak else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duzenleme hatasi: {str(e)}")

@app.post("/guncelle/kapak")
def sarki_kapak_guncelle(sarki_adi: str, file: UploadFile = File(...)):
    if not sarki_adi.endswith('.mp3'):
        raise HTTPException(status_code=400, detail="Sarki adi .mp3 ile bitmelidir.")
        
    sarki_yolu = os.path.join(MUSIC_DIR, sarki_adi)
    if not os.path.exists(sarki_yolu):
        raise HTTPException(status_code=404, detail="Kapak yuklenmek istenen sarki bulunamadi.")
        
    temiz_ad = sarki_adi.replace('.mp3', '')
    
    dosya_uzantisi = os.path.splitext(file.filename)[1].lower()
    if dosya_uzantisi not in ['.jpg', '.jpeg', '.png', '.webp']:
        raise HTTPException(status_code=400, detail="Gecersiz resim formati. Sadece jpg, jpeg, png, webp desteklenir.")
        
    try:
        dosyalar = os.listdir(MUSIC_DIR)
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            eski_kapak = f"{temiz_ad}{ext}"
            if eski_kapak in dosyalar:
                os.remove(os.path.join(MUSIC_DIR, eski_kapak))
                
        yeni_kapak_adi = f"{temiz_ad}{dosya_uzantisi}"
        yeni_kapak_yolu = os.path.join(MUSIC_DIR, yeni_kapak_adi)
        
        with open(yeni_kapak_yolu, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return {
            "durum": "basarili", 
            "mesaj": "Kapak resmi basariyla yenilendi.", 
            "kapak_url": f"/kapak/{yeni_kapak_adi}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kapak yukleme hatasi: {str(e)}")

# ==========================================
# YENİ EKLEME: SARKİ VE İLİŞİK TEMİZLEME KAPISI
# ==========================================

@app.delete("/sil")
def sarki_sil(data: SilmeModel):
    if not data.sarki_adi.endswith('.mp3'):
        raise HTTPException(status_code=400, detail="Sarki adi .mp3 ile bitmelidir.")
        
    sarki_yolu = os.path.join(MUSIC_DIR, data.sarki_adi)
    if not os.path.exists(sarki_yolu):
        raise HTTPException(status_code=404, detail="Silinmek istenen sarki dosyasi bulunamadi.")
        
    temiz_ad = data.sarki_adi.replace('.mp3', '')
    silinen_kapak_var_mi = False
    
    try:
        # 1. Ana MP3 dosyasını diskten sil
        os.remove(sarki_yolu)
        
        # 2. Bu şarkıyla aynı isme sahip olan kapak resmini bul ve onu da sil
        dosyalar = os.listdir(MUSIC_DIR)
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            kapak_adi = f"{temiz_ad}{ext}"
            if kapak_adi in dosyalar:
                os.remove(os.path.join(MUSIC_DIR, kapak_adi))
                silinen_kapak_var_mi = True
                break  # Kapak bulundu ve silindi, döngüden çık
                
        return {
            "durum": "basarili",
            "mesaj": f"'{data.sarki_adi}' ve ilişkili tüm dosyalar başarıyla sunucudan kazındı.",
            "kapak_silindi_mi": silinen_kapak_var_mi
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Silme islemi sirasinda hata olustu: {str(e)}")
