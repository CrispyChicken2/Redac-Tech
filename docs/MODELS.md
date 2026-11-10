# Language models

RedacTech works without any language model. A model is an optional helper for two things: reading a request written
in plain French or English (free text), and, if asked, rephrasing the status lists of the assistant. In both cases the
model only proposes: code checks every operation (quotes, values taken from the request, existing parts and
documents) and a writer decides every change. Nothing here is sent outside your machine.

## The model in use

| Setting | Value | Where |
|---|---|---|
| Provider | `none` (default), `ollama`, `fake` (tests only) | `config.toml`, `[llm] provider` |
| Model | `ministral-3:8b` | `config.toml`, `[llm] model` |
| Temperature | `0` | `[llm] temperature` |
| Retries on an invalid answer | `2` | `[llm] max_retries` |
| Time limit of a call | `120` seconds | `[llm] timeout_s` |

`ministral-3:8b` is a local model under the Apache 2.0 licence that handles French and English. Changing the model is
one line: edit `[llm] model` (all the calls to a model are in `src/redactech/llm/`, nowhere else). To use it, set
`provider = "ollama"`.

## Install Ollama and pull the model

1. Install Ollama from its public site (https://ollama.com), for your system. It runs a server on this machine,
   `http://localhost:11434`. RedacTech only talks to that address: any other host is refused unless the environment
   variable `REDACTECH_ALLOW_REMOTE_LLM=1` is set.
2. Pull the model once (this downloads several gigabytes):

   ```bash
   ollama pull ministral-3:8b
   ```

   `OllamaProvider.ensure_model()` can do the same pull, once, when a program asks for it; it is never called when
   RedacTech starts or in the tests of the continuous integration.
3. Set `provider = "ollama"` under `[llm]` in `config.toml`. In the interface, the "Texte libre" area then appears
   under the request; on the command line use `redactech request --text "..."`. With `provider = "none"` they say that
   free text needs the local model.

The log of every model call of a run (time, model, a hash of the prompt, duration, ok or the error; never the prompt
itself) is written to `runs/<id>/llm_calls.jsonl`.

## Run the tests that use the real model

The continuous integration never calls a model: it uses recorded answers (`tests/llm_cassettes/`). The tests that need
Ollama carry the marker `ollama` and are skipped unless you opt in:

```bash
REDACTECH_OLLAMA=1 pytest -m ollama      # on Windows PowerShell: $env:REDACTECH_OLLAMA = "1"; pytest -m ollama
```

They need the server running and the model pulled; they may download it through `ensure_model()`. They check that a
clear request gives the same result as the mapping table, and that an incomplete request never writes an invented value.

## Latency

| Call | Model | Machine | Median | Worst |
|---|---|---|---|---|
| Free-text request (about 1,000 tokens) | `ministral-3:8b` | to be measured on the target PC | not measured | not measured |
| Rephrasing of a status list | `ministral-3:8b` | to be measured on the target PC | not measured | not measured |

Not measured: Ollama is not installed on the build machine. Measure on the target PC with `REDACTECH_OLLAMA=1 pytest -m
ollama --durations=10` and fill the table; the time limit of a call (`timeout_s`) may need raising on a slow machine.
