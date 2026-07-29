from app.services.facebook_downloader import FacebookDownloader


IMAGE_URL = (
    "https://scontent-vie1-1.xx.fbcdn.net/v/t39.99422-6/"
    "749923977_2804934759889216_665972284892399069_n.png"
    "?stp=dst-jpg_tt6&cstp=mx1200x1200&ctp=p526x296"
    "&_nc_cat=103&ccb=1-7&_nc_sid=127cfc"
    "&_nc_ohc=N4_kIXh9F6EQ7kNvwGmDF4Q"
    "&_nc_oc=Adrgb96jgBCT7wp_uPOe9aUGQe5Hf2Tp4MsZwlDEENPFzkixC4UNdwOlbvSN6f0738sTfnPpstlx8nbDS5-Z6RLm"
    "&_nc_zt=14&_nc_ht=scontent-vie1-1.xx"
    "&_nc_gid=1ZVNJMfpCID5nx0D4EF9AA"
    "&_nc_ss=7b289"
    "&oh=00_AQChjuw8LxjC4wxdbWf3zy2kjsot_BnjbtUHFYTfolr7kA"
    "&oe=6A6CE65B"
)

downloader = FacebookDownloader()

print("Lade Bild herunter...")

file_path = downloader.download_image(IMAGE_URL)

print("\nBild gespeichert unter:")
print(file_path)