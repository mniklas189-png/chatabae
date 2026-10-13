import re

MEDIA = r"(?:bild|foto|selfie|portr[aä]t|image|picture|pic|photo|portrait)"


def explicit_image_request(text: str) -> bool:
    head = text.strip()[:240].casefold()
    if re.search(r"\b(?:kein(?:e|en|em|es)?|nicht|don't|do not)\b", head):
        return False
    polite = r"^(?:(?:bitte|please|can you|could you|kannst du)\s+)*"
    create = polite + r"(?:erstelle|generiere|zeichne|mach(?:e)?|create|generate|draw|make)\b.{0,100}\b" + MEDIA + r"\b"
    # "Send/show me a picture", "schick/zeig mir ein Foto" ask the character for an image of the current moment.
    send = polite + r"(?:schick(?:e)?|send(?:e)?|zeig(?:e)?|show)\s+(?:mir|me)\b.{0,60}\b" + MEDIA + r"\b"
    return bool(re.search(create, head) or re.search(send, head))
