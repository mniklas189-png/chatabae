"""Read-only verification of the deployed Pages shell and its public API setting."""
import re

import httpx


def main():
    with httpx.Client(timeout=20) as client:
        response = client.get("https://mniklas189-png.github.io/chatabae/")
        response.raise_for_status()
        scripts = re.findall(r'src="([^"]+\.js)"', response.text)
        if not scripts or not all(path.startswith("/chatabae/assets/") for path in scripts):
            raise RuntimeError("Deployed script paths do not match the Pages base")
        bundle = client.get("https://mniklas189-png.github.io" + scripts[0])
        bundle.raise_for_status()
        if "https://niklas-pc.taila668dd.ts.net" not in bundle.text:
            raise RuntimeError("Deployed frontend is missing the configured Funnel origin")
        if "C:\\Users\\" in bundle.text or "auth-secret" in bundle.text:
            raise RuntimeError("A private runtime reference appeared in the static build")
        print({"pages_html": response.status_code, "javascript": bundle.status_code, "base_path_ok": True, "api_origin_configured": True})


if __name__ == "__main__":
    main()
