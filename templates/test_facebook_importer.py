from app.services.facebook_importer import FacebookImporter


URL = (
    "https://www.facebook.com/fpoenoe/posts/"
    "pfbid02HCFUdB5ycDBSgptrM227RDLxDn894s75ezh951V4QuBfud6y2WMJV7xwtZadAUTsl"
)


importer = FacebookImporter(
    profile_dir="playwright_profile",
    headless=False,
)

print("Facebook-Beitrag wird importiert ...")

beitrag = importer.import_from_url(URL)

print("\n===== TEXT =====\n")
print(beitrag.text)

print("\n===== BILDER =====\n")

if beitrag.images:
    for nummer, bild_url in enumerate(beitrag.images, start=1):
        print(f"Bild {nummer}:")
        print(bild_url)
        print()
else:
    print("Keine Bilder gefunden.")

print("\n===== QUELLE =====\n")
print(beitrag.source_url)

input("\nDrücke ENTER zum Beenden ...")