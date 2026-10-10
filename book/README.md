# Book PDFs ↔ code folders

The code folders follow an earlier draft's chapter numbering, so they don't match the
published book. Each code folder holds the book pages its code belongs to, matched by the
code printed in the book (listings found verbatim in the folder) and by subject matter.

| Code folder | Book chapter(s) | Book pages |
|---|---|---|
| `chapters/ch02` | 1 KGs and LLMs: a killer combination · 2 Intelligent systems: a hybrid approach | 31–66 |
| `chapters/ch03` | 3 Create your first knowledge graph from ontologies | 67–94 |
| `chapters/ch04` | 4 From simple networks to multisource integration | 95–124 |
| `chapters/ch05` | Appendix C Building knowledge graphs from structured sources (miRNA) | 491–522 |
| `chapters/ch06` | — not in the published book (BBC news / spaCy NER / Louvain topics) | — |
| `chapters/ch07` | 5 Extracting domain-specific knowledge from unstructured data | 125–144 |
| `chapters/ch08` | 6 Building knowledge graphs with large language models | 145–158 |
| `chapters/ch09` | 7 Named entity disambiguation | 159–209 |
| `chapters/ch10` | 8 NED with open LLMs and domain ontologies | 210–236 |
| `chapters/ch11` | 9 Machine learning on knowledge graphs: a primer approach | 237–262 |
| `chapters/ch12` | 10 Graph feature engineering: manual and semiautomated approaches | 263–301 |
| `chapters/ch13` | 11 Graph representation learning and graph neural networks | 302–331 |
| `chapters/ch14` | 12 Node classification and link prediction with GNNs | 332–364 |
| `chapters/ch15` | 13 Knowledge graph–powered retrieval-augmented generation | 365–385 |
| `chapters/ch17` | 14 Asking a KG questions with natural language · 15 Building a QA agent with LangGraph | 386–464 |

Part divider pages are included with the first chapter of each part.

Not tied to one folder (kept here in `book/`): front matter (1–30), appendix A Introduction
to graphs (465–476), appendix B Neo4j (477–490, setup for the whole repo), references
(523–534), index (535–544).

Notes on shared code: chapter 7 reuses the HPO importer from `ch03` and scispaCy entity
linking similar to `ch05`; chapter 8 reuses the SNOMED importers from `ch09` (each folder
ships its own copy).
