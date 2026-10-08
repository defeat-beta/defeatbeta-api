"""Refresh the README dataset badge and render its download message in bold."""

import argparse
import math
from pathlib import Path
import re
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "doc/badges/hugging-face-downloads.svg"
BADGE_URL = "https://img.shields.io/badge/dynamic/xml?" + urlencode({
    "url": "https://modelpulse.ifsp.dev/badge/dataset/defeatbeta/yahoo-finance-data.svg",
    "query": '(//*[local-name()="text"])[2]',
    "label": "Hugging Face Dataset",
    "prefix": "downloads ",
    "suffix": "/month",
    "color": "FFD21E",
    "labelColor": "111318",
    "style": "flat-square",
    "cacheSeconds": "3600",
})


def fetch_badge():
    request = Request(BADGE_URL, headers={"User-Agent": "DefeatBeta-README-Badge/1.0"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def build_badge(source):
    root = ET.fromstring(source)
    ns = {"svg": SVG_NS}
    texts = root.findall(".//svg:text", ns)
    rects = root.findall(".//svg:rect", ns)
    if root.tag != f"{{{SVG_NS}}}svg" or len(texts) != 2 or len(rects) != 2:
        raise ValueError("Unexpected source badge structure")
    label, message = texts
    if label.text != "Hugging Face Dataset" or not re.fullmatch(
        r"downloads [\d.,]+[kKMB]?/month", message.text or ""
    ):
        raise ValueError("Source badge does not contain a valid monthly download count")
    if [rect.attrib.get("fill", "").upper() for rect in rects] != ["#111318", "#FFD21E"]:
        raise ValueError("Source badge colors do not match the README design")
    if any(node.tag in {f"{{{SVG_NS}}}linearGradient", f"{{{SVG_NS}}}radialGradient"} for node in root.iter()):
        raise ValueError("Source badge must not contain a gradient")
    if any("opacity" in rect.attrib or "fill-opacity" in rect.attrib for rect in rects):
        raise ValueError("Source badge must use opaque backgrounds")
    if root.attrib.get("height") != "20" or message.attrib.get("transform") != "scale(.1)":
        raise ValueError("Unexpected source badge text scale")

    label_width = int(rects[0].attrib["width"])
    regular_text_width = float(message.attrib.pop("textLength")) / 10
    # Leave extra space for natural bold glyph widths instead of compressing the text.
    message_width = math.ceil(regular_text_width * 1.15) + 10
    root.set("width", str(label_width + message_width))
    rects[1].set("width", str(message_width))
    message.set("x", str((label_width + message_width / 2) * 10))
    message.set("font-weight", "700")
    content = ET.tostring(root, encoding="utf-8") + b"\n"
    if not content.isascii():
        raise ValueError("Badge output must contain only ASCII content")
    return content


def update_badge(output=DEFAULT_OUTPUT):
    content = build_badge(fetch_badge())
    output = Path(output)
    if output.exists() and output.read_bytes() == content:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    changed = update_badge(args.output)
    print("Dataset downloads badge updated." if changed else "Dataset downloads badge unchanged.")


if __name__ == "__main__":
    main()
