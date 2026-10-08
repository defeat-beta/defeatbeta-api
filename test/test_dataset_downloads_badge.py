import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
import xml.etree.ElementTree as ET

from scripts import update_dataset_downloads_badge as badge


def source_badge(count="129k", text_length=1310):
    message = f"downloads {count}/month"
    return f'''<svg xmlns="{badge.SVG_NS}" width="272" height="20" role="img"
        aria-label="Hugging Face Dataset: {message}">
      <title>Hugging Face Dataset: {message}</title>
      <g shape-rendering="crispEdges">
        <rect width="131" height="20" fill="#111318"/>
        <rect x="131" width="141" height="20" fill="#ffd21e"/>
      </g>
      <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="110">
        <text x="665" y="140" textLength="1210" transform="scale(.1)">Hugging Face Dataset</text>
        <text x="2005" y="140" textLength="{text_length}" transform="scale(.1)" fill="#333">{message}</text>
      </g>
    </svg>'''.encode("ascii")


class TestDatasetDownloadsBadge(unittest.TestCase):
    def test_only_download_message_is_bold(self):
        root = ET.fromstring(badge.build_badge(source_badge()))
        texts = root.findall(f".//{{{badge.SVG_NS}}}text")
        self.assertNotIn("font-weight", texts[0].attrib)
        self.assertEqual(texts[1].attrib["font-weight"], "700")
        self.assertEqual(texts[1].text, "downloads 129k/month")
        self.assertNotIn("textLength", texts[1].attrib)
        self.assertEqual(root.attrib["aria-label"], "Hugging Face Dataset: downloads 129k/month")

    def test_bold_text_has_extra_room_and_solid_original_yellow(self):
        root = ET.fromstring(badge.build_badge(source_badge()))
        rects = root.findall(f".//{{{badge.SVG_NS}}}rect")
        self.assertGreater(int(rects[1].attrib["width"]), 141)
        self.assertEqual(int(root.attrib["width"]), sum(int(rect.attrib["width"]) for rect in rects))
        self.assertEqual(rects[1].attrib["fill"].upper(), "#FFD21E")
        self.assertFalse(root.findall(f".//{{{badge.SVG_NS}}}linearGradient"))

    def test_counts_and_message_width_can_change(self):
        for count in ("0", "999", "1.2k", "129k", "3.4M", "1.2B", "123,456"):
            with self.subTest(count=count):
                root = ET.fromstring(badge.build_badge(source_badge(count)))
                message = root.findall(f".//{{{badge.SVG_NS}}}text")[-1]
                self.assertEqual(message.text, f"downloads {count}/month")
                self.assertEqual(message.attrib["font-weight"], "700")
        narrow = ET.fromstring(badge.build_badge(source_badge("0", 1000)))
        wide = ET.fromstring(badge.build_badge(source_badge("123,456", 1600)))
        self.assertLess(int(narrow.attrib["width"]), int(wide.attrib["width"]))

    def test_invalid_source_is_rejected(self):
        sources = [
            b"<svg/>",
            source_badge("unavailable"),
            source_badge().replace(b"#ffd21e", b"#f8d44e"),
            source_badge().replace(b'<rect x="131"', b'<rect opacity="0.5" x="131"'),
            source_badge().replace(b"<title>", b'<linearGradient id="s"/><title>'),
        ]
        for source in sources:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    badge.build_badge(source)

    def test_refresh_skips_unchanged_content(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "badge.svg"
            with patch.object(badge, "fetch_badge", return_value=source_badge()):
                self.assertTrue(badge.update_badge(output))
                first_content = output.read_bytes()
                self.assertFalse(badge.update_badge(output))
                self.assertEqual(output.read_bytes(), first_content)
            with patch.object(badge, "fetch_badge", return_value=source_badge("130k")):
                self.assertTrue(badge.update_badge(output))
                self.assertIn(b"downloads 130k/month", output.read_bytes())

    def test_failed_refresh_preserves_previous_badge(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "badge.svg"
            previous = badge.build_badge(source_badge())
            output.write_bytes(previous)
            with patch.object(badge, "fetch_badge", side_effect=URLError("Unavailable")):
                with self.assertRaises(URLError):
                    badge.update_badge(output)
            self.assertEqual(output.read_bytes(), previous)
            with patch.object(badge, "fetch_badge", return_value=source_badge("unavailable")):
                with self.assertRaises(ValueError):
                    badge.update_badge(output)
            self.assertEqual(output.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
