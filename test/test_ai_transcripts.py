import logging
import unittest
from pathlib import Path

from defeatbeta_api.client.openai_conf import OpenAIConfiguration
from defeatbeta_api.data.ticker import Ticker
from openai import OpenAI

class TestAITranscripts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ticker = Ticker("META", http_proxy="http://127.0.0.1:33210", log_level=logging.DEBUG)

        key = Path(__file__).parent.joinpath("siliconflow_api.key").read_text(encoding="utf-8")
        cls.llm = OpenAI(
            api_key=key,
            base_url="https://api.siliconflow.cn/v1"
        )

    @classmethod
    def tearDownClass(cls):
        result = cls.ticker.download_data_performance()
        print(result)

    def test_summarize_key_financial_data_with_ai(self):
        transcripts = self.ticker.earning_call_transcripts()
        res = transcripts.summarize_key_financial_data_with_ai(
            2025,
            2,
            self.llm,
            OpenAIConfiguration(model='Qwen/Qwen3-8B', temperature=0))
        print(res.to_string())

    def test_analyze_financial_metrics_change_for_this_quarter_with_ai(self):
        transcripts = self.ticker.earning_call_transcripts()
        res = transcripts.analyze_financial_metrics_change_for_this_quarter_with_ai(
            2025,
            3,
            self.llm,
            OpenAIConfiguration(model='Qwen/Qwen3-Omni-30B-A3B-Thinking', temperature=0, top_p=0, tool_choice="auto"))
        print(res.to_string())

    def test_analyze_financial_metrics_forecast_for_future_with_ai(self):
        transcripts = self.ticker.earning_call_transcripts()
        res = transcripts.analyze_financial_metrics_forecast_for_future_with_ai(
            2025,
            3,
            self.llm,
            OpenAIConfiguration(model='Qwen/Qwen3-Omni-30B-A3B-Thinking', temperature=0, top_p=0, tool_choice="auto"))
        print(res.to_string())