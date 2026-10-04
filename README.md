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
| 3 | [chapters/ch03/Readme.md](chapters/ch03/Readme.md) | HPO knowledge graph from an ontology: [overview diagram](chapters/ch03/ch03_overview.png), [importer steps](chapters/ch03/Readme.md#what-the-importer-does), [Cypher listings](chapters/ch03/Readme.md#the-cypher-listings), [Docker setup](chapters/ch03/Readme.md#docker) |
| 4 | [chapters/ch04/Readme.md](chapters/ch04/Readme.md) | Protein-interaction graph and community analysis: [overview diagram](chapters/ch04/ch04_overview.png), [analysis algorithm](chapters/ch04/Readme.md#the-analysis-algorithm-in-detail), [Cypher listings](chapters/ch04/Readme.md#the-cypher-listings), [Docker setup](chapters/ch04/Readme.md#docker) |
| 5 | [chapters/ch05/Readme.md](chapters/ch05/Readme.md) | Build a knowledge graph from structured sources: install, [download and import the datasets](chapters/ch05/Readme.md#download-the-datasets), [reconcile diseases](chapters/ch05/Readme.md#reconcile-diseases), [notes for Mac users](chapters/ch05/Readme.md#notes-for-mac-users) |
| 6 | [chapters/ch06/Readme.md](chapters/ch06/Readme.md) | Knowledge graphs and natural language processing: [importing the datasets](chapters/ch06/Readme.md#import-the-datasets), cached requests |
| 8 | [chapters/ch08/Readme.md](chapters/ch08/Readme.md) | Building knowledge graphs with large language models: [importing the datasets](chapters/ch08/Readme.md#import-the-datasets), cached LLM responses |
| 9 | [chapters/ch09/Readme.md](chapters/ch09/Readme.md) | Named entity disambiguation with UMLS ontologies: [download the datasets](chapters/ch09/Readme.md#download-the-datasets), [import them](chapters/ch09/Readme.md#import-the-datasets), [notes for Mac users](chapters/ch09/Readme.md#notes-for-mac-users) |
| 10 | [chapters/ch10/Readme.md](chapters/ch10/Readme.md) | Named entity disambiguation with open LLMs and domain ontologies: [Neo4j settings](chapters/ch10/Readme.md#neo4j-settings), [Ollama settings](chapters/ch10/Readme.md#ollama-settings), [SNOMED ontology](chapters/ch10/Readme.md#download-the-snomed-ontology), [disambiguation](chapters/ch10/Readme.md#perform-disambiguation) |
| 14 | [chapters/ch14/Readme.md](chapters/ch14/Readme.md) | Node classification and link prediction with GNNs: PyTorch Geometric notebooks (Colab links) |
| 17 | [chapters/ch17/Readme.md](chapters/ch17/Readme.md) | Question answering system using LangGraph and Streamlit: [download the investigative graph](chapters/ch17/Readme.md#download-the-investigative-graph), [launch the application](chapters/ch17/Readme.md#launch-the-application) |
