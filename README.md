<img src="docs/assets/logo.png" alt="WeRDeep Logo" />

# WeRDeep

High-performance deep web search and research engine optimized for AI agent orchestration. WeRDeep is architected as a multi-tier system with a native orchestration layer, a Python/Cython application core, and a TypeScript integration bridge.

---

## System Architecture

### 1. Orchestration Tier (`py2c`)
A compiled C wrapper (`src/wrapper/py2c.c`) that serves as the primary lifecycle management engine. It abstracts complex environment setup, build pipelines, and release engineering into a unified interface.
*   **Responsibilities**: Venv orchestration, system dependency resolution, native extension compilation, and cross-platform release assembly.
*   **Implementation**: C (utilizing `libft` for utility functions).

### 2. Application Core (`werdeep`)
The logic tier implementing the search and crawl pipelines.
*   **Search Layer**: Orchestrates discovery backends (e.g., DuckDuckGo) with query staggering and result normalization.
*   **Crawl Engine**: Scrapy-based asynchronous spidering with dynamic relevance pruning.
*   **Processing Tier**: Native Cython extensions (`parser.pyx`, `formatter.pyx`) for high-throughput HTML-to-structured-data transformation.

### 3. Integration Tier (`opencode`)
The bridge between the WeRDeep engine and AI agent platforms.
*   **Tool Wrapper**: TypeScript-based definition (`src/opencode/tool/werdeep.ts`) providing a schema-validated interface for agent tool calls.
*   **Execution**: Invokes the compiled WeRDeep core via subprocess orchestration.

---

## Developer & Contributor Workflow

The `py2c` wrapper simplifies all development tasks. It is the mandatory entry point for contributors.

### Commands
| Command | Responsibility |
| :--- | :--- |
| `./py2c setup` | Resolves system dependencies (GCC, Python, Bun, UPX) and bootstraps the environment. |
| `./py2c build` | Orchestrates the full local lifecycle: venv creation, Cython compilation, linting, and multi-tier testing. |
| `./py2c verify` | Performs structural integrity checks to ensure project state consistency. |
| `./py2c assembleRelease` | Generates optimized, cross-platform binaries with optional UPX compression. |
| `./py2c clean` | Purges all build artifacts, virtual environments, and temporary caches. |

### Local Environment Setup
```bash
./py2c setup
./py2c build
source .build-venv/bin/activate
```

---

## Technical Stack

*   **Orchestration**: C (GCC/Clang)
*   **Core Engine**: Python 3.11+, Scrapy 2.11+
*   **Performance Extensions**: Cython 3.0+
*   **Validation**: JSONSchema
*   **Integration**: TypeScript 5.x, Bun

---

## Data Contracts

WeRDeep enforces strict, immutable dataclasses for all I/O operations to ensure machine-readable predictability.

### Input: `SearchRequest`
| Field | Type | Description |
| :--- | :--- | :--- |
| `query` | `str` | Target keywords or seed URL. |
| `format` | `str` | Output format (`json`, `markdown`, `html`, `text`). |
| `depth` | `int` | Recursion depth (1-5). |
| `max_pages` | `int` | Page processing limit. |

### Output: `SearchResult`
| Field | Type | Description |
| :--- | :--- | :--- |
| `status` | `str` | `success`, `error`, or `partial`. |
| `results` | `list` | Array of extracted objects including code blocks and metadata. |
| `metadata` | `dict` | Execution metrics (latency, page counts, depth achieved). |

---

## Implementation Notes

*   **Native Optimization**: Core extraction logic is compiled to C via Cython, minimizing Python overhead during concurrent operations.
*   **Release Engineering**: `py2c assembleRelease` supports targeting `linux`, `windows`, `macos`, and `macos-arm64`.
*   **Residency**: Stateless execution model. All temporary data is confined to the session's memory or current working directory.
*   **Compliance**: Built-in `robots.txt` enforcement with configurable whitelist overrides.
