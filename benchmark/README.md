# DefeatBeta Performance Challenge

> **How fast can a serverless data lake become?**

## Background

Data lakes are powerful — but they are also intimidating.

If you have ever tried to build one, you probably know the drill:

**S3 → Hive Metastore → Spark → Presto/Trino → Data Catalog → IAM → ...**

Before the first dataset is even queryable, you are already deep inside infrastructure.

But what if you do not need all of that?

What if you are a researcher, an independent developer, or simply a data enthusiast who wants a **simple, free, and maintenance-free way to store and query large datasets**?

This is the idea behind what I call a:

> **Poor Man's Data Lake**

DefeatBeta API is built around this idea.

Its architecture is intentionally simple:

```text
Hugging Face
    │
    │  Parquet over HTTP
    ▼
  DuckDB
    │
    ▼
Application
```

The data is hosted on Hugging Face, the query engine runs locally, and Parquet files are queried directly over HTTP.

There is:

* no database server
* no Spark cluster
* no data warehouse
* no always-on infrastructure to maintain
* almost no hosting cost

Just:

> **Files + HTTP + a query engine**

Simple. Cheap. Serverless.

But simplicity comes with a price:

> **The network is now part of the query engine.**

Remote reads, HTTP latency, metadata access, Parquet layout, data transfer, caching, query planning, and execution can all become bottlenecks.

That leads to the question behind this project:

> **How far can we push this architecture before we hit its fundamental performance limit?**

---

## The Challenge

Use **Systems Engineering + First Principles Thinking** to push DefeatBeta's query performance as far as possible.

For now, the primary benchmark is:

> **Cold Query Latency**

No warm-cache advantage. The goal is to optimize the latency of a real query when the required data is not already available locally.

Explore aggressively. Measure everything. Question every implementation detail.

But there is one fundamental constraint.

---

## Principles

### Do not change the architecture

This is the most important rule.

The architecture must remain:

```text
Remote Parquet on Hugging Face
            +
         HTTP
            +
      Local DuckDB
```

The goal is **not** to make the benchmark fast by turning DefeatBeta into another architecture.

Do not solve the problem by introducing:

* a traditional database server
* a data warehouse
* a Spark/Trino cluster
* a persistent query service
* a separately operated backend
* a full local copy of the dataset

The challenge is to discover how fast the **existing serverless architecture itself** can become.

Everything inside that boundary is open to optimization.

Parquet layout, HTTP behavior, range requests, metadata access, concurrency, caching strategies, prefetching, DuckDB configuration, query planning, indexes, execution strategies, and implementation details can all be challenged.

### Measure, don't guess

Every optimization should be validated by reproducible benchmark results.

The question is not whether an idea sounds faster.

The question is:

> **Did it make the cold query faster?**

### Optimize end to end

Microbenchmarks are useful for understanding bottlenecks, but the final metric is end-to-end query latency.

An optimization only matters if it improves the actual query.

---

The architecture stays.

Everything else is fair game.

**Let's find its limit.**

---
