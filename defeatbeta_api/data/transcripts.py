import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

import pandas as pd
from openai import OpenAI
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from tabulate import tabulate

from defeatbeta_api.client.openai_conf import OpenAIConfiguration
from defeatbeta_api.utils.util import load_transcripts_summary_prompt_temp, load_transcripts_summary_tools_def, \
    unit_map, load_transcripts_analyze_change_prompt, load_transcripts_analyze_change_tools, \
    load_transcripts_analyze_forecast_prompt, load_transcripts_analyze_forecast_tools, nltk_sentences


def _unnest(record: pd.DataFrame) -> pd.DataFrame:
    transcripts_data = record["transcripts"].iloc[0]
    df_paragraphs = pd.json_normalize(transcripts_data)
    return df_paragraphs

@dataclass
class Transcripts:
    def __init__(self, ticker: str, transcripts: pd.DataFrame, log_level: str):
        self.ticker = ticker
        self.transcripts = transcripts
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s %(levelname)s %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            stream=sys.stdout
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_transcripts_list(self) -> pd.DataFrame:
        return self.transcripts

    def get_transcript(self, fiscal_year: int, fiscal_quarter: int) -> pd.DataFrame:
        record = self._find_transcripts(fiscal_quarter, fiscal_year)
        if record.empty:
            raise ValueError(f"No transcript found for FY{fiscal_year} Q{fiscal_quarter}")
        df_paragraphs = _unnest(record)
        return df_paragraphs

    def analyze_financial_metrics_forecast_for_future_with_ai(self, fiscal_year: int, fiscal_quarter: int, llm: OpenAI, config: Optional[OpenAIConfiguration] = None) -> pd.DataFrame:
        conf = config if config is not None else OpenAIConfiguration()
        template = load_transcripts_analyze_forecast_prompt()
        pattern_transcripts = r"\{earnings_call_transcripts\}"
        transcript = self.get_transcript(fiscal_year, fiscal_quarter)
        transcript_json = transcript.to_dict(orient="records")
        for paragraph in transcript_json:
            content = paragraph.pop("content")
            sentences = nltk_sentences(content)
            paragraph["sentences"] = sentences
        transcript_str = json.dumps(transcript_json, ensure_ascii=False, indent=2)
        prompt = re.sub(pattern_transcripts, transcript_str, template)

        messages = [{
            "role": "system",
            "content": "You are a precise financial analyst. Your task is to analyze every single sentence in the `sentences` array of the provided `earnings_call_transcripts`."
            },
            {
                'role': 'user',
                'content': prompt
            }]
        tools = load_transcripts_analyze_forecast_tools()

        start = time.perf_counter()
        response = llm.chat.completions.create(
            model=conf.get_model(),
            messages=messages,
            temperature=conf.get_temperature(),
            top_p=conf.get_top_p(),
            stream=True,
            tools=tools,
            tool_choice=conf.get_tool_choice()
        )

        if not response:
            raise ValueError(f"Invalid response from LLM: {response}")

        raw_args = ""
        prompt_tokens = 0
        reasoning_tokens = 0
        completion_tokens = 0
        cursor_char = "▌"
        panel_title = "[bold green]🧠 Thinking Step by Step[/]"
        max_lines = 8
        reasoning_text = ""
        console = Console()
        is_tty = sys.stdout.isatty()
        with Live(console=console, refresh_per_second=20) as live:
            for chunk in response:
                delta = chunk.choices[0].delta

                if hasattr(chunk, "usage") and chunk.usage and chunk.choices[0].finish_reason:
                    prompt_tokens = getattr(chunk.usage, "prompt_tokens", 0)
                    completion_tokens = getattr(chunk.usage, "completion_tokens", 0)
                    details = getattr(chunk.usage, "completion_tokens_details", None)
                    if details and hasattr(details, "reasoning_tokens"):
                        reasoning_tokens = details.reasoning_tokens

                if delta.reasoning_content:
                    if is_tty:
                        reasoning_text += delta.reasoning_content
                        lines = reasoning_text.splitlines()
                        visible_text = "\n".join(lines[-max_lines:])
                        live.update(Panel(visible_text + " " + cursor_char, title=panel_title, border_style="green",
                                          padding=(1, 2)))
                    else:
                        print(delta.reasoning_content, end="", flush=True)

                if delta.tool_calls:
                    raw_args += f"{delta.tool_calls[0].function.arguments}"
            if is_tty:
                live.update(Panel(reasoning_text, title="[bold white]🧠 Finish Think[/]", border_style="white",
                                  padding=(1, 2)))

        end = time.perf_counter()
        elapsed = (end - start)

        if raw_args == "":
            raise ValueError(f"No tool call was made by the model. Raw message: {raw_args}")

        try:
            clean_args = raw_args.split("</tool_call>")[0].strip()
            if isinstance(clean_args, str):
                open_braces = clean_args.count('{')
                close_braces = clean_args.count('}')
                if open_braces > close_braces:
                    clean_args += '}' * (open_braces - close_braces)
                elif close_braces > open_braces:
                    clean_args = clean_args.rstrip('}' * (close_braces - open_braces))
                func_args = json.loads(clean_args)
            else:
                func_args = raw_args
        except Exception as e:
            raise ValueError(
                f"Failed to parse tool_call arguments: {raw_args}, error: {e}"
            )

        final_metrics = func_args.get("key_sentences")

        self.logger.debug(
            f"metrics data: {func_args}, "
            f"prompt tokens: {prompt_tokens}, "
            f"reasoning tokens: {reasoning_tokens}, "
            f"completion tokens: {completion_tokens}, "
            f"infer elapsed(s): {round(elapsed, 2)}"
        )

        df = pd.DataFrame(final_metrics)

        records = []
        for index, row in df.iterrows():
            records.append({
                "symbol": self.ticker,
                "fiscal_year": fiscal_year,
                "fiscal_quarter": fiscal_quarter,
                "speaker": row['speaker'],
                "paragraph_number": row['paragraph_number'],
                "summary": row['short_summary'],
                "outlook": row['sentence'],
                "attitude": row['attitude'],
                "reason": row['reason']
            })
        return pd.DataFrame(records)

    def analyze_financial_metrics_change_for_this_quarter_with_ai(self, fiscal_year: int, fiscal_quarter: int, llm: OpenAI, config: Optional[OpenAIConfiguration] = None) -> pd.DataFrame:
        conf = config if config is not None else OpenAIConfiguration()
        template = load_transcripts_analyze_change_prompt()
        pattern_transcripts = r"\{earnings_call_transcripts\}"
        transcript = self.get_transcript(fiscal_year, fiscal_quarter)
        transcript_json = transcript.to_dict(orient="records")
        for paragraph in transcript_json:
            content = paragraph.pop("content")
            sentences = nltk_sentences(content)
            paragraph["sentences"] = sentences
        transcript_str = json.dumps(transcript_json, ensure_ascii=False, indent=2)
        prompt = re.sub(pattern_transcripts, transcript_str, template)

        messages = [{
                        "role": "system",
                        "content": "You are a precise financial analyst. Your task is to analyze every single sentence in the `sentences` array of the provided `earnings_call_transcripts`."
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }]
        tools = load_transcripts_analyze_change_tools()

        start = time.perf_counter()
        response = llm.chat.completions.create(
            model=conf.get_model(),
            messages=messages,
            temperature=conf.get_temperature(),
            top_p=conf.get_top_p(),
            stream=True,
            tools=tools,
            tool_choice=conf.get_tool_choice()
        )

        if not response:
            raise ValueError(f"Invalid response from LLM: {response}")

        raw_args = ""
        prompt_tokens = 0
        reasoning_tokens = 0
        completion_tokens = 0
        cursor_char = "▌"
        panel_title = "[bold green]🧠 Thinking Step by Step[/]"
        max_lines = 8
        reasoning_text = ""
        console = Console()
        is_tty = sys.stdout.isatty()
        with Live(console=console, refresh_per_second=20) as live:
            for chunk in response:
                delta = chunk.choices[0].delta

                if hasattr(chunk, "usage") and chunk.usage and chunk.choices[0].finish_reason:
                    prompt_tokens = getattr(chunk.usage, "prompt_tokens", 0)
                    completion_tokens = getattr(chunk.usage, "completion_tokens", 0)
                    details = getattr(chunk.usage, "completion_tokens_details", None)
                    if details and hasattr(details, "reasoning_tokens"):
                        reasoning_tokens = details.reasoning_tokens

                if delta.reasoning_content:
                    if is_tty:
                        reasoning_text += delta.reasoning_content
                        lines = reasoning_text.splitlines()
                        visible_text = "\n".join(lines[-max_lines:])
                        live.update(Panel(visible_text + " " + cursor_char, title=panel_title, border_style="green",
                                          padding=(1, 2)))
                    else:
                        print(delta.reasoning_content, end="", flush=True)
                if delta.tool_calls:
                    raw_args += f"{delta.tool_calls[0].function.arguments}"

            if is_tty:
                live.update(Panel(reasoning_text, title="[bold white]🧠 Finish Think[/]", border_style="white",
                                  padding=(1, 2)))

        end = time.perf_counter()
        elapsed = (end - start)

        if raw_args == "":
            raise ValueError(f"No tool call was made by the model. Raw message: {raw_args}")

        try:
            clean_args = raw_args.split("</tool_call>")[0].strip()
            if isinstance(clean_args, str):
                open_braces = clean_args.count('{')
                close_braces = clean_args.count('}')
                if open_braces > close_braces:
                    clean_args += '}' * (open_braces - close_braces)
                elif close_braces > open_braces:
                    clean_args = clean_args.rstrip('}' * (close_braces - open_braces))
                func_args = json.loads(clean_args)
            else:
                func_args = raw_args
        except Exception as e:
            raise ValueError(
                f"Failed to parse tool_call arguments: {raw_args}, error: {e}"
            )

        final_metrics = func_args.get("key_sentences")

        self.logger.debug(
            f"metrics data: {func_args}, "
            f"prompt tokens: {prompt_tokens}, "
            f"reasoning tokens: {reasoning_tokens}, "
            f"completion tokens: {completion_tokens}, "
            f"infer elapsed(s): {round(elapsed, 2)}"
        )

        df = pd.DataFrame(final_metrics)

        records = []
        for index, row in df.iterrows():
            if row['is_factual'] == 'N':
                continue

            records.append({
                "symbol": self.ticker,
                "fiscal_year": fiscal_year,
                "fiscal_quarter": fiscal_quarter,
                "speaker": row['speaker'],
                "paragraph_number": row['paragraph_number'],
                "summary": row['short_summary'],
                "sentence": row['sentence'],
                "direction": row['direction'],
                "reason": row['reason']
            })
        return pd.DataFrame(records)

    def summarize_key_financial_data_with_ai(self, fiscal_year: int, fiscal_quarter: int, llm: OpenAI, config: Optional[OpenAIConfiguration] = None) -> pd.DataFrame:
        conf = config if config is not None else OpenAIConfiguration()
        template = load_transcripts_summary_prompt_temp()

        pattern_question = r"\{question\}"
        pattern_transcripts = r"\{earnings_call_transcripts\}"
        transcript = self.get_transcript(fiscal_year, fiscal_quarter)
        transcript_json = transcript.to_dict(orient="records")
        transcript_str = json.dumps(transcript_json, ensure_ascii=False, indent=2)

        prompt = re.sub(pattern_question,
                        "Extract the key financial data required for function calling tools based on the earnings call transcript",
                        template)
        prompt = re.sub(pattern_transcripts, transcript_str, prompt)

        tools = load_transcripts_summary_tools_def()

        messages = [{
            'role': 'user',
            'content': prompt
        }]

        start = time.perf_counter()
        response = llm.chat.completions.create(
            model = conf.get_model(),
            messages = messages,
            temperature = conf.get_temperature(),
            top_p = conf.get_top_p(),
            stream = False,
            tools = tools,
            tool_choice=conf.get_tool_choice()
        )
        end = time.perf_counter()
        elapsed = (end - start)

        if not response or not response.choices:
            raise ValueError(f"Invalid response from LLM: {response}")

        message = response.choices[0].message

        if not hasattr(message, "tool_calls") or not message.tool_calls:
            raise ValueError(f"No tool call was made by the model. Raw message: {message}")

        for tool_call in message.tool_calls:
            try:
                raw_args = tool_call.function.arguments.strip()
                clean_args = raw_args.split("</tool_call>")[0].strip()
                if isinstance(clean_args, str):
                    open_braces = clean_args.count('{')
                    close_braces = clean_args.count('}')
                    if open_braces > close_braces:
                        clean_args += '}' * (open_braces - close_braces)
                    elif close_braces > open_braces:
                        clean_args = clean_args.rstrip('}' * (close_braces - open_braces))
                    func_args = json.loads(clean_args)
                else:
                    func_args = raw_args
            except Exception as e:
                raise ValueError(
                    f"Failed to parse tool_call arguments: {tool_call.function.arguments}, error: {e}"
                )

            key_financial_data = func_args.get("key_financial_data")
            if not key_financial_data:
                raise ValueError(
                    f"'key_financial_data' missing in func_args: {func_args}"
                )

            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            self.logger.debug(
                f"Key financial data: {key_financial_data}, "
                f"prompt tokens: {prompt_tokens}, "
                f"completion tokens: {completion_tokens}, "
                f"infer elapsed(s): {round(elapsed, 2)}"
            )

            records = []
            for k, v in key_financial_data.items():
                if v is None:
                    value = None
                    currency_code = None
                    speaker = None
                    paragraph_number = None
                else:
                    try:
                        if v.get("unit") == '%':
                            value = round(float(v["value_vocabulary"]) / 100, 4)
                        elif v.get("unit") == 'per_share':
                            value = round(float(v["value_vocabulary"]), 4)
                        else:
                            value = float(v["value_vocabulary"]) * unit_map.get(v.get("unit"), 1)
                        currency_code = v.get("currency_code")
                        speaker = v.get("speaker")
                        paragraph_number = str(v.get("paragraph_number"))
                    except Exception as e:
                        raise ValueError(f"Bad value in {k}: {v}, error: {e}")

                metric = k
                time_scope = "raw"
                if k.endswith("_for_this_quarter"):
                    metric = k[: -len("_for_this_quarter")]
                    time_scope = "this_quarter"
                elif k.endswith("_for_next_quarter"):
                    metric = k[: -len("_for_next_quarter")]
                    time_scope = "next_quarter"
                elif k.endswith("_for_full_fiscal_year"):
                    metric = k[: -len("_for_full_fiscal_year")]
                    time_scope = "full_fiscal_year"

                records.append({
                    "symbol": self.ticker,
                    "fiscal_year": fiscal_year,
                    "fiscal_quarter": fiscal_quarter,
                    "speaker": speaker,
                    "paragraph_number": paragraph_number,
                    "key_financial_metric": metric,
                    "time_scope": time_scope,
                    "value": value,
                    "currency_code": currency_code
                })

            df = pd.DataFrame(records)
            return df

    def print_pretty_table(self, fiscal_year: int, fiscal_quarter: int) -> str:
        record = self._find_transcripts(fiscal_quarter, fiscal_year)
        if record.empty:
            raise ValueError(f"No transcript found for FY{fiscal_year} Q{fiscal_quarter}")
        report_date = record["report_date"].iloc[0]
        df_paragraphs = _unnest(record)
        title = f"Earnings Call Transcripts FY{fiscal_year} Q{fiscal_quarter} (Reported on {report_date})\n"
        table = tabulate(df_paragraphs, headers="keys", tablefmt="grid", showindex=False)
        print(title + table)

    def __str__(self):
        return self.transcripts.to_string(columns=["symbol", 'fiscal_year', "fiscal_quarter", "report_date"])

    def _find_transcripts(self, fiscal_quarter, fiscal_year):
        mask = (self.transcripts['fiscal_year'] == fiscal_year) & \
               (self.transcripts['fiscal_quarter'] == fiscal_quarter)
        record = self.transcripts.loc[mask]
        return record