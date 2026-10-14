"""Opt-in observations outside timing, plus separately marked warm profiles."""

import cProfile
import gc
from pathlib import Path
import pstats


def validate_options(case):
    options = case.get("diagnostics", {})
    repeats = options.get("profile_repeats", 0)
    if type(repeats) is not int or repeats < 0:
        raise ValueError("Profile repetitions must be a nonnegative integer")
    if repeats and (case["kind"] != "single" or case["state"] != "memory_warm"):
        raise ValueError("Profiles require one fully warmed API call")
    return options


def memory_sample(process, stage, filesystem=None, client=None):
    sample = {"stage": stage, "rss_bytes": process.memory_info().rss,
              "threads": process.num_threads()}
    if filesystem is not None:
        with filesystem._guard:
            sample["cache_data_bytes"] = sum(map(len, filesystem._memory_blocks.values()))
            sample["cache_footer_bytes"] = sum(len(value[1]) for value in filesystem._footer_memory.values())
    if client is not None and client.connection is not None:
        # This extra SQL runs after the timed batch and pending downloads.
        sample["duckdb_memory"] = client.connection.execute(
            "SELECT tag, memory_usage_bytes, temporary_storage_bytes FROM duckdb_memory()"
        ).fetchall()
    return sample


def profile_calls(call, repeats):
    profile = cProfile.Profile()
    with profile:
        for _ in range(repeats):
            result = call()
    stats = []
    for (filename, line, function), (primitive, calls, own, cumulative, _) in pstats.Stats(profile).stats.items():
        # Keep locations useful without depending on the runner's absolute path.
        path = Path(filename)
        parts = path.parts
        for package in ("defeatbeta_api", "benchmark"):
            if package in parts:
                filename = Path(*parts[parts.index(package):]).as_posix()
                break
        else:
            filename = path.name
        stats.append({"file": filename, "line": line, "function": function,
                      "primitive_calls": primitive, "calls": calls,
                      "own_seconds": own, "cumulative_seconds": cumulative})
    return result, {"repetitions": repeats,
                    "scope": "Caller-thread cProfile; native calls can include waiting; instrumented timing",
                    "functions": sorted(stats, key=lambda row: row["cumulative_seconds"], reverse=True)}


def collect_memory(process, stage):
    gc.collect()
    return memory_sample(process, stage)
