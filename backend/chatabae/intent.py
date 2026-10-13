import re


def explicit_image_request(text: str) -> bool:
    head = text.strip()[:240].casefold()
    if re.search(r"\b(?:kein(?:e|en|em|es)?|nicht|don't|do not)\b", head):
        return False
    return bool(re.search(r"^(?:(?:bitte|please|can you|kannst du)\s+)*(?:erstelle|generiere|zeichne|mach(?:e)?|create|generate|draw|make)\b.{0,100}\b(?:bild|foto|portr[aä]t|image|picture|photo|portrait)\b", head))
