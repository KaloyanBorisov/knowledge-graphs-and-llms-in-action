# Knowledge Graph Applied

### Getting started with this repository

Make sure that the Neo4j instance you want to use is up and running. Follow the instructions Appendix B for installation directions.

Update the [config.ini](config.ini) file with the relevant neo4j credentials.

It is reccomanded to set up a python virtual environment for this project. For example:
```shell
$ python -m venv venv
```

Unless otherwise stated, the code in this repo is tested with python version 3.8/3.9/3.10

Chapters make use of a `MakeFiles` based approach to simplfy operations, make sure you can run 
the make command:

```shell
$ make -version
```

Generally the `GNU make` is available on many package managers for a wide range of OSes.

```shell
$ choco install make # Windows Os
$ apt install make # Debian & derivated OSes (including ubuntu)
$ yum install make # Centos 
```

macOS's users should have `make` available through XCode - Command line tools:

```shell
$ xcode-select --install
```
alteratively  `GNU Make` can be installed via brew
```shell
brew install make
```

For further information refere to the Readme.md available in each chapter's directory

### Chapter guides

| Chapter | Guide | Highlights |
|---------|-------|------------|
| 2 | [chapters/ch02/Readme.md](chapters/ch02/Readme.md) | Knowledge graphs and LLMs (no code): [KGs vs. LLMs](chapters/ch02/Readme.md#knowledge-graphs-vs-llms), [recap of intelligent advisor systems](chapters/ch02/Readme.md#background-intelligent-advisor-systems-recap-of-chapter-1), [example prompts](chapters/ch02/Readme.md#the-listings) |
| 3 | [chapters/ch03/Readme.md](chapters/ch03/Readme.md) | HPO knowledge graph from an ontology: [overview diagram](chapters/ch03/images/ch03_overview.png), [importer steps](chapters/ch03/Readme.md#what-the-importer-does), [Cypher listings](chapters/ch03/Readme.md#the-cypher-listings), [Docker setup](chapters/ch03/Readme.md#docker) |
| 4 | [chapters/ch04/Readme.md](chapters/ch04/Readme.md) | Protein-interaction graph and community analysis: [overview diagram](chapters/ch04/images/ch04_overview.png), [analysis algorithm](chapters/ch04/Readme.md#the-analysis-algorithm-in-detail), [Cypher listings](chapters/ch04/Readme.md#the-cypher-listings), [Docker setup](chapters/ch04/Readme.md#docker) |
| 4 (App. C) | [chapters/ch04_Appendix_C/Readme.md](chapters/ch04_Appendix_C/Readme.md) | Build a knowledge graph from structured sources: install, [download and import the datasets](chapters/ch04_Appendix_C/Readme.md#download-the-datasets), [reconcile diseases](chapters/ch04_Appendix_C/Readme.md#reconcile-diseases), [notes for Mac users](chapters/ch04_Appendix_C/Readme.md#notes-for-mac-users) |
| 5a | [chapters/ch05_a/Readme.md](chapters/ch05_a/Readme.md) | Knowledge graphs and natural language processing: [importing the datasets](chapters/ch05_a/Readme.md#import-the-datasets), cached requests |
| 5b | [chapters/ch05_b/Readme.md](chapters/ch05_b/Readme.md) | Extracting domain-specific knowledge from unstructured data: [getting started](chapters/ch05_b/Readme.md#getting-started), [the listings](chapters/ch05_b/Readme.md#the-listings) (UBIAI annotation, OpenAI prompt-based extraction), [prompt refinement](chapters/ch05_b/Readme.md#how-the-prompt-improves-from-2-to-7) |
| 6 | [chapters/ch06/Readme.md](chapters/ch06/Readme.md) | Building knowledge graphs with large language models: [importing the datasets](chapters/ch06/Readme.md#import-the-datasets), cached LLM responses |
| 7 | [chapters/ch07/Readme.md](chapters/ch07/Readme.md) | Named entity disambiguation with UMLS ontologies: [download the datasets](chapters/ch07/Readme.md#download-the-datasets), [import them](chapters/ch07/Readme.md#import-the-datasets), [notes for Mac users](chapters/ch07/Readme.md#notes-for-mac-users) |
| 8 | [chapters/ch08/Readme.md](chapters/ch08/Readme.md) | Named entity disambiguation with open LLMs and domain ontologies: [Neo4j settings](chapters/ch08/Readme.md#neo4j-settings), [Ollama settings](chapters/ch08/Readme.md#ollama-settings), [SNOMED ontology](chapters/ch08/Readme.md#download-the-snomed-ontology), [disambiguation](chapters/ch08/Readme.md#perform-disambiguation) |
| 12 | [chapters/ch12/Readme.md](chapters/ch12/Readme.md) | Node classification and link prediction with GNNs: PyTorch Geometric notebooks (Colab links) |
| 14 | [chapters/ch14/Readme.md](chapters/ch14/Readme.md) | Question answering system using LangGraph and Streamlit: [download the investigative graph](chapters/ch14/Readme.md#download-the-investigative-graph), [launch the application](chapters/ch14/Readme.md#launch-the-application) |
