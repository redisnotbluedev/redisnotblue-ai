import random

def get_browser_headers(referer, origin=None):
	"""Returns 2026-compliant evasive browser headers."""
	chrome_ver = f"13{random.randint(4, 7)}"
	headers = {
		"User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver}.0.0.0 Safari/537.36",
		"Accept": "application/json, text/plain, */*",
		"Accept-Language": "en-US,en;q=0.9",
		"Sec-Ch-Ua": f'"Not(A:Brand";v="99", "Google Chrome";v="{chrome_ver}", "Chromium";v="{chrome_ver}"',
		"Sec-Ch-Ua-Mobile": "?0",
		"Sec-Ch-Ua-Platform": '"Windows"',
		"Sec-Fetch-Dest": "empty",
		"Sec-Fetch-Mode": "cors",
		"Sec-Fetch-Site": "same-origin",
		"Priority": "u=1, i",
		"Referer": referer
	}
	if origin: headers["Origin"] = origin
	return headers
