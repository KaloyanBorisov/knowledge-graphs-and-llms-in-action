## Knowledge graphs and natural language processing

### Getting started

#### Install requirements
This chapter's `Makefile` assumes you have a virtual environemnt folder called `venv` 
at the reopository root folder. You can edit the`Makefile` and redefine the `PIP` variable
at the first line to match your configuration.
```shell
make init
```

#### Import the datasets
Run this command to execute the importer code.
```shell
make import
```

##### Cached requests

During the enrichment steps, many requests are made to the Wikidata REST API. 
As do any public APIs, the Wikidata REST API has certain rate limits in place to prevent misuse and abuse. 
To be considerate of these limits, the enrichment steps include important throttling mechanisms that slow down the process.

To mitigate this performance issue while still maintaining some flexibility, responses from Wikidata API requests are cached 
so that each request is issued at most once. 
Afterward, the cached file representing the response is used instead. 
This behavior is enabled by default and the cached responses are available in this Git repository. 
As a result, even the first time the process runs, it will use the cached Wikidata responses, resulting in quick execution.

This behavior can be overridden by simply removing one or more JSON files in the `cache_org` and/or the `cache_owners` 
subfolder of the `data` folder.

Please note that using the cached responses provided in this repository does not guarantee that not a single request will 
be issued to the Wikidata API. 
The output of the Spacy pipeline may differ slightly depending on the model version used, 
and it is possible that entities that are not cached may be added.

### Running with Docker

No local Python environment is needed. From this folder:

```shell
make docker-up       # start Neo4j 5 + Graph Data Science (browser: http://localhost:7474, neo4j / password)
make docker-import   # build the importer image and run steps 1-3 (safe to repeat)
make docker-down     # stop (add -v to `docker compose down` to wipe the graph)
```

The `importer` service reads the BBC articles from `../../data` and writes the Wikidata caches back to it.
Three small demo services run the spaCy listings and show the result in a browser:

```shell
docker compose run --rm --service-ports depparse   # listing 5a.1 -> http://localhost:5000
docker compose run --rm --service-ports nerdemo    # listing 5a.2 -> http://localhost:5001
docker compose run --rm --service-ports rulerdemo # listing 5a.3 -> http://localhost:5002
```

### What the importer builds

| Step | Script | Result in the graph |
|---|---|---|
| 1 | `importer/step1__import_bbc.py` | `Topic` → `Document` → entity nodes (`Person`, `Organization`, `Location`, `Date`, `Money`, `Number`, `NatReligPolitGroup`, `WorkOfArt`) via `MENTIONS_*`, then `Keyword` nodes via `MENTIONS_KEYWORD {rank}` |
| 2 | `importer/step2__enrich_organizations.py` | Organizations mentioned in more than 4 articles get `description`, `wikidata_id`, `wikidata_url`, plus `HAS_SUBSIDIARY`, `MEMBER_OF`, `IN_INDUSTRY` |
| 3 | `importer/step3__enrich_by_ownerships.py` | `OWNED_BY_ORG` / `OWNED_BY_PER` to nodes labelled `Owner` (Wikidata property P127) |

Each script starts with a docstring explaining its logic in detail.

### Listings

The `listings/` folder holds the code from the book. The `5a.1`–`5a.3` files are Python demos of the NLP
building blocks; the `5a.10`–`5a.16` files are Cypher queries to paste into Neo4j Browser **after** `make import`,
in numeric order. They turn the graph into topics: keyword overlap → document similarity → communities → topic terms.

#### NLP building blocks (Python, spaCy)

All three analyse the same sentence: *"Jane Austen, the Victorian era writer, works nowadays for Google."*

- **5a.1 – NLP with dependency parsing.** Loads `en_core_web_sm`, parses the sentence and serves a diagram of the
  grammar (`displacy`, style `dep`). Under each word you see its part of speech (morphology); the arrows show which word
  depends on which (syntax): *Austen* is the subject of *works*, *for Google* attaches to *works*, *writer* renames
  *Austen*. This is the raw material for relation extraction ("Austen works for Google"), which the importer does *not* do.
- **5a.2 – NER pipeline.** Runs the same model and prints each named entity with its label and a plain-English
  explanation (`Jane Austen PERSON`, `Victorian NORP`, `Google ORG`), then serves a highlighted view (style `ent`).
  This is exactly what step 1 does for every article; the labels become the node types in the graph.
  `en_core_web_md` is a larger, usually more accurate alternative (commented out).
- **5a.3 – Dictionary-based NER.** Adds an `entity_ruler` to the pipeline with a rule-based pattern
  (`LEMMA: writer` → label `TITLE`), so the model also tags job titles that its statistical NER does not know.
  Rules and the statistical model can be combined: use rules for domain vocabulary, the model for everything else.

#### Document similarity and topics (Cypher)

The idea: two articles about the same subject share keywords. Link such articles, let a graph algorithm find dense groups,
and describe each group by its characteristic terms.

- **5a.10 – Remove meaningless keywords.** Deletes generic keywords ("first", "second", "last year", ...) that TextRank
  extracts but that say nothing about a topic and would create false similarities.
- **5a.11 – Jaccard similarities.** For every pair of documents sharing more than 2 keywords, computes
  *Jaccard similarity* = shared keywords / all distinct keywords of both, and stores it on
  `(:Document)-[:SIMILAR_TO {similarity}]-(:Document)`. The shared-keyword threshold keeps the number of edges manageable.
- **5a.12 – Get similar documents.** Takes one document (`business_173`), picks its 10 most similar neighbours and returns
  the paths through the keywords they share, so you can see *why* they are considered similar in Neo4j Browser.
- **5a.13 – Graph projection for GDS.** Copies the `Document` nodes and `SIMILAR_TO` edges (as undirected, weighted by
  `similarity`) into an in-memory graph named `undirectedDocs`. Graph Data Science algorithms run on projections, not on
  the stored graph. Needs the GDS plugin (already installed in the Docker setup).
- **5a.14 – Run Louvain.** Runs the Louvain community detection algorithm on the projection, weighted by similarity, and
  writes a `community` id onto every `Document`. Louvain is unsupervised: it finds groups from the structure alone,
  without any predefined categories.
- **5a.15 – Assign documents to communities.** For communities with more than 4 documents, creates a `Community` node
  (with `n_docs`) and `(:Document)-[:BELONGS_TO]->(:Community)`. Tiny communities are ignored as noise.
- **5a.16 – Significant terms and topic descriptions.** Scores each keyword inside a community by how much more frequent
  it is there than in the whole corpus, and stores the top 30 as `Community.significant_terms`. These terms describe the
  topic of the community. The query reads `Keyword.n_docs` (number of documents mentioning the keyword) and
  `Keyword.doc_freq` (that number divided by the total number of documents), which **the importer does not create**.
  Run this first (not part of the original listing; syntax-checked but I did not run it):

  ```cypher
  MATCH (d:Document) WITH count(d) AS total
  MATCH (k:Keyword)<-[:MENTIONS_KEYWORD]-(d2:Document)
  WITH k, count(d2) AS n, total
  SET k.n_docs = n, k.doc_freq = 1.0 * n / total
  ```

Exercise 3 (`exercises/exercise_3.txt`) is the same pipeline with cosine similarity instead of Jaccard (needs GDS).

### Exercises

- **exercise_1.py** – extends listing 5a.3 with rules for job titles such as "Chief data officer" and "CEO"
  (token patterns and a regex).
- **exercise_2.py** – queries Wikidata for a person's date of birth, occupations, fields of work and owned companies,
  to enrich `Person` nodes the way step 2 enriches organizations. It connects to `bolt://localhost:7687`, so with Docker
  it works from the host (port 7687 is published).
