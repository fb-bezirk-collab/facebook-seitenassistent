from pathlib import Path

from playwright.sync_api import sync_playwright


URL = (
    "https://www.facebook.com/fpoenoe/posts/"
    "pfbid02HCFUdB5ycDBSgptrM227RDLxDn894s75ezh951V4QuBfud6y2WMJV7xwtZadAUTsl"
)

PROFILE_DIR = Path("playwright_profile")


with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        viewport={"width": 1400, "height": 1000},
    )

    page = context.pages[0] if context.pages else context.new_page()

    bild_urls = set()

    def log_response(response):
        url = response.url.lower()

        if (
            "scontent" in url
            and (
                ".jpg" in url
                or ".jpeg" in url
                or ".png" in url
                or ".webp" in url
            )
        ):
            bild_urls.add(response.url)

    page.on("response", log_response)

    print("Öffne Facebook ...")

    page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=60_000,
    )

    page.wait_for_timeout(5000)

    print("\nSeitentitel:")
    print(page.title())

    print("\nAktuelle URL:")
    print(page.url)

    print("\nSuche den eigentlichen Beitrag ...")

    beitraege = page.locator("div[role='article']")
    anzahl_beitraege = beitraege.count()

    print(f"Gefundene Beitragsbereiche: {anzahl_beitraege}")

    if anzahl_beitraege == 0:
        print("Kein Beitragsbereich gefunden.")

    else:
        beitrag = beitraege.first

        print("\n===== MÖGLICHE TEXTBLÖCKE =====\n")

        textbloecke = beitrag.locator("div[dir='auto']").all_inner_texts()

        bereinigte_textbloecke = []

        for text in textbloecke:
            text = text.strip()

            if not text:
                continue

            if text in bereinigte_textbloecke:
                continue

            if text in {
                "Gefällt mir",
                "Kommentieren",
                "Teilen",
                "Antworten",
                "Alle Kommentare ansehen",
                "Weitere Kommentare anzeigen",
            }:
                continue

            bereinigte_textbloecke.append(text)

        for nummer, text in enumerate(bereinigte_textbloecke, start=1):
            print(f"\n--- Textblock {nummer} ---")
            print(text)

        print("\n===== GROSSE BILDER IM BEITRAG =====\n")

        bilder = beitrag.locator("img").evaluate_all(
            """
            elements => elements
                .map(img => ({
                    src: img.currentSrc || img.src,
                    alt: img.alt || "",
                    width: img.naturalWidth,
                    height: img.naturalHeight
                }))
                .filter(img =>
                    img.src &&
                    img.naturalWidth >= 500 &&
                    img.naturalHeight >= 500
                )
            """
        )

        if not bilder:
            print("Keine großen Bilder gefunden.")

        else:
            for nummer, bild in enumerate(bilder, start=1):
                print(
                    f"{nummer}: "
                    f"{bild['width']}x{bild['height']} | "
                    f"Alt: {bild['alt'][:150]} | "
                    f"{bild['src']}"
                )

    print("\n===== GELADENE BILDER =====\n")

    if not bild_urls:
        print("Keine Bild-URLs im Netzwerkverkehr gefunden.")

    else:
        for url in sorted(bild_urls):
            print(url)

    input("\nDrücke ENTER zum Beenden ...")

    context.close()