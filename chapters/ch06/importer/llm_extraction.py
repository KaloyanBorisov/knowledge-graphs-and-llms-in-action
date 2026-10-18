"""
llm_extraction.py - STAGE 2: Named-Entity + Relation extraction with an LLM.

Aspect: *LLM interaction* (prompting, caching, parsing, retry orchestration).
It never writes Cypher itself - persistence is delegated to
`GraphStoreMixin.store_to_neo4j` (graph_store.py).

Expected LLM output (JSON):
    {
      "entities":  {"<label>": [{"id": ..., "name": ..., ...}, ...], ...},
      "relations": {"<relation type>": [{"source": <entity id>, "target": <entity id>, ...}, ...], ...}
    }
"""
import json
import logging
import os
import time
from pathlib import Path

from openai import OpenAI

from pipeline_logging import run_query

logger = logging.getLogger(__name__)


class LLMExtractionMixin:
    """
    Mixin for `FullKG`. Relies on attributes provided by the host class:
        self.openai_model, self.openai_key, self.openai_url, self.cache_folder
        self.llm_stats   dict of counters: cache_hits, api_calls, prompt_tokens, completion_tokens
        self._driver, self._database           (from BaseImporter)
        self.store_to_neo4j(...)               (from GraphStoreMixin)
    """

    # ------------------------------------------------------------------ prompt

    def read_prompt(self, path: Path):
        """
        Load the three prompt parts from `path`:
            task            -> system message (instructions, output schema)
            example         -> one example input page   (few-shot, user turn)
            example_output  -> the desired output for it (few-shot, assistant turn)
        """
        logger.info("Reading prompt files from %s", path)
        prompt_segments = {}
        with open(os.path.join(path, "gpt_prompt_task.txt"), 'r') as f:
            prompt_segments['task'] = f.read()
        with open(os.path.join(path, "gpt_prompt_example.txt"), 'r') as f:
            prompt_segments['example'] = f.read()
        with open(os.path.join(path, "gpt_prompt_example_output.txt"), 'r') as f:
            prompt_segments['example_output'] = f.read()
        logger.info("Prompt loaded (%s)",
                    ", ".join(f"{k}={len(v)} chars" for k, v in prompt_segments.items()))
        return prompt_segments

    # ------------------------------------------------------------------ LLM call

    def openai_query(self, gpt_client, prompt_segments: dict, query: str, key: str = None):
        """
        Send one page to the LLM and return the raw text answer.

        :param gpt_client: an `openai.OpenAI` client
        :param prompt_segments: output of `read_prompt`
        :param query: the page text
        :param key: cache key (the page id). When given together with `self.cache_folder`,
                    the answer is read from / written to `<cache_folder>/<key>.json`,
                    so re-runs cost no API calls.
        """
        # --- 1. cache hit? ---------------------------------------------------
        if self.cache_folder is not None and key is not None:
            if (self.cache_folder / f"{key}.json").is_file():
                self.llm_stats['cache_hits'] += 1
                logger.info("Cache HIT for %s", key)
                return json.load((self.cache_folder / f"{key}.json").open())
            logger.info("Cache MISS for %s - calling model '%s'", key, self.openai_model)

        # --- 2. build a one-shot chat: system task + example Q/A + the real page ---
        messages = [{"role": "system", "content": prompt_segments['task']},
                    {"role": "user", "content": prompt_segments['example']},
                    {"role": "assistant", "content": prompt_segments['example_output']},
                    {"role": "user", "content": query}
                    ]

        # --- 3. call the model: temperature 0 => (near-)deterministic extraction ----
        t_start = time.time()
        response = gpt_client.chat.completions.create(model=self.openai_model, messages=messages, temperature=0.,
                                                      max_tokens=2000)
        ret = response.choices[0].message.content
        self.llm_stats['api_calls'] += 1
        usage = getattr(response, 'usage', None)
        if usage is not None:
            self.llm_stats['prompt_tokens'] += usage.prompt_tokens
            self.llm_stats['completion_tokens'] += usage.completion_tokens
        logger.info("LLM answered for %s in %.1f sec (finish_reason=%s, tokens prompt=%s completion=%s)",
                    key, time.time() - t_start, response.choices[0].finish_reason,
                    getattr(usage, 'prompt_tokens', '?'), getattr(usage, 'completion_tokens', '?'))
        if response.choices[0].finish_reason == "length":
            logger.warning("Answer for %s was cut off by max_tokens - the JSON will probably be invalid", key)
        logger.debug("Raw LLM answer for %s:\n%s", key, ret)

        # --- 4. write to cache (only if the cache folder exists) ---------------
        if self.cache_folder is not None and key is not None:
            if self.cache_folder.is_dir():
                json.dump(ret, (self.cache_folder / f"{key}.json").open("w"))
                logger.debug("Cached answer for %s", key)
            else:
                logger.warning("Cache folder %s does not exist - answer for %s not cached", self.cache_folder, key)

        return ret

    # ------------------------------------------------------------------ parsing

    @staticmethod
    def parse_gpt_output(output: str) -> dict:
        """
        Turn the raw LLM text into flat lists of entities and relations.

        Returns {'entities': [...], 'relations': [...], 'failed': bool}.
        `failed` is True when the text is not valid JSON or lacks the
        'entities'/'relations' keys; the caller then retries the page.
        """
        ents, rels = list(), list()
        failed = False
        try:
            d = json.loads(output)
            if 'entities' not in d or 'relations' not in d:
                logger.warning("GPT output does not have expected format (missing 'entities'/'relations'): %s", d)
                failed = True
            else:
                for label, arr in d['entities'].items():
                    for e in arr:
                        # keep the label exactly as the LLM wrote it ...
                        e['label_gpt'] = label
                        # ... and a clean TitleCase one usable as a Neo4j label:
                        # "research  topic" -> "ResearchTopic"
                        e['label'] = "".join([x[0].upper() + x[1:].lower() for x in label.strip().split()])
                        ents.append(e)
                for rel_type, arr in d['relations'].items():
                    for r in arr:
                        # Some relations carry their own "type" attribute (e.g. kind of
                        # conversation). It would clash with the relation type below,
                        # so preserve it under a different name.
                        if 'type' in r:
                            r['conversation_type'] = r['type']
                        r['type_gpt'] = rel_type
                        # "talked to" -> "TALKED_TO"
                        r['type'] = "_".join(rel_type.strip().upper().split())
                        rels.append(r)
        except Exception as e:
            logger.warning("Couldn't parse GPT output: %s\nOutput was:\n%s", e, output)
            failed = True
        return {'entities': ents, 'relations': rels, 'failed': failed}

    # ------------------------------------------------------------------ orchestration

    def process_diaries_gpt(self, query_read: str, gpt_prompt_segments: dict, n_docs: int = 100,
                            run: str = "run 1"):
        """
        Run the extraction over not-yet-processed pages and store the results.

        :param query_read: Cypher returning `id` (internal node id), `key` (page id), `text`;
                           must accept a `$limit` parameter and skip `:GPTProcessed` pages
        :param gpt_prompt_segments: output of `read_prompt`
        :param n_docs: max number of pages handled in this call
        :param run: label stored on the created edges (`runs` list) to tell repeated
                    extraction runs apart (see GraphStoreMixin.cleanse_stability_test)
        """
        logger.info("LLM settings: model=%s base_url=%s api_key_set=%s cache_folder=%s", self.openai_model,
                    self.openai_url, bool(self.openai_key), self.cache_folder)
        if not self.openai_key:
            logger.warning("OPENAI_KEY is not set - only pages whose answer is already cached can be processed")
        client = OpenAI(
            base_url=self.openai_url,
            api_key=self.openai_key,
        )

        # --- read the batch of pages to process ------------------------------------
        with self._driver.session(database=self._database) as session:
            pages = run_query(session, f"Reading up to {n_docs} unprocessed pages", query_read, limit=n_docs)
        logger.info("Read %d pages to process", len(pages))
        if not pages:
            logger.warning("No unprocessed pages found (all pages already carry :GPTProcessed?)")

        # --- first pass: strict - store a page only if its output parsed cleanly ----
        failed_pages = list()
        for i, p in enumerate(pages, start=1):
            logger.info("[%d/%d] Processing page %s", i, len(pages), p['key'])
            output = self.openai_query(client, gpt_prompt_segments, p['text'], key=p['key'])
            gpt_parsed = self.parse_gpt_output(output)
            logger.debug("Parsed output of %s: %s", p['key'], gpt_parsed)
            if gpt_parsed['failed']:
                logger.warning("[%d/%d] Page %s has an invalid LLM output - queued for retry", i, len(pages), p['key'])
                failed_pages.append(p)
            else:  # store only fully-correct outputs, rerun the pages with failures later
                logger.info("[%d/%d] Storing %d entities and %d relations from page %s to Neo4j", i, len(pages),
                            len(gpt_parsed['entities']), len(gpt_parsed['relations']), p['key'])
                self.store_to_neo4j(p['id'], gpt_parsed['entities'], gpt_parsed['relations'], run)

        logger.info("First pass finished: %d pages processed, %d pages had output format issues",
                    len(pages), len(failed_pages))
        if len(failed_pages) == 0:
            self._log_llm_stats()
            return

        # --- second pass: retry failed pages once, lenient - keep whatever parsed ----
        logger.info("Rerunning %d pages with failures ...", len(failed_pages))

        for i, p in enumerate(failed_pages, start=1):
            logger.info("[retry %d/%d] Processing page %s", i, len(failed_pages), p['key'])
            # "_retry" suffix => a separate cache entry, otherwise the broken answer
            # would simply be served from the cache again.
            output = self.openai_query(client, gpt_prompt_segments, p['text'], key=p['key'] + "_retry")
            gpt_parsed = self.parse_gpt_output(output)
            if gpt_parsed['failed']:
                logger.error("[retry %d/%d] Page %s failed again; storing only what could be parsed",
                             i, len(failed_pages), p['key'])
            # even if some relations have incorrect format again, store at least the good ones this time
            logger.info("[retry %d/%d] Storing %d entities and %d relations from page %s to Neo4j", i,
                        len(failed_pages), len(gpt_parsed['entities']), len(gpt_parsed['relations']), p['key'])
            self.store_to_neo4j(p['id'], gpt_parsed['entities'], gpt_parsed['relations'], run)
        self._log_llm_stats()

    def _log_llm_stats(self):
        """One-line summary of cache usage and API consumption of this run."""
        s = self.llm_stats
        logger.info("LLM usage: api_calls=%d cache_hits=%d prompt_tokens=%d completion_tokens=%d",
                    s['api_calls'], s['cache_hits'], s['prompt_tokens'], s['completion_tokens'])
