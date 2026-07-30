import unittest
from unittest.mock import patch

import nltk

from defeatbeta_api.utils.util import nltk_sentences


class TestNltkSentences(unittest.TestCase):

    @patch("defeatbeta_api.utils.util.validate_nltk_directory", return_value="/tmp/test-nltk")
    @patch("defeatbeta_api.utils.util.nltk.sent_tokenize")
    @patch("defeatbeta_api.utils.util.nltk.download")
    @patch("defeatbeta_api.utils.util.nltk.data.find")
    def test_uses_existing_tokenizer_without_download(
        self,
        find,
        download,
        sent_tokenize,
        validate_directory,
    ):
        sent_tokenize.return_value = ["One.", "Two."]

        with patch.object(nltk.data, "path", []):
            result = nltk_sentences("One. Two.")

        self.assertEqual(result, ["One.", "Two."])
        find.assert_called_once_with(
            "tokenizers/punkt_tab/english",
            paths=["/tmp/test-nltk"],
        )
        download.assert_not_called()
        sent_tokenize.assert_called_once_with("One. Two.")
        validate_directory.assert_called_once_with()

    @patch("defeatbeta_api.utils.util.validate_nltk_directory", return_value="/tmp/test-nltk")
    @patch("defeatbeta_api.utils.util.nltk.sent_tokenize")
    @patch("defeatbeta_api.utils.util.nltk.download")
    @patch(
        "defeatbeta_api.utils.util.nltk.data.find",
        side_effect=LookupError("missing tokenizer"),
    )
    def test_downloads_tokenizer_only_when_needed(
        self,
        find,
        download,
        sent_tokenize,
        validate_directory,
    ):
        sent_tokenize.return_value = ["One.", "Two."]

        with patch.object(nltk.data, "path", []):
            result = nltk_sentences("One. Two.")

        self.assertEqual(result, ["One.", "Two."])
        download.assert_called_once_with(
            "punkt_tab",
            download_dir="/tmp/test-nltk",
            quiet=True,
            raise_on_error=True,
        )
        sent_tokenize.assert_called_once_with("One. Two.")


if __name__ == "__main__":
    unittest.main()
