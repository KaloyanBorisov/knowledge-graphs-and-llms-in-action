"""
Step 1 - build the base knowledge graph from the BBC news dataset.

What this script does (two passes over the data, each implemented as a BaseImporter subclass):

  Pass 1  BBCImporter         reads data/bbc/<topic>/<n>.txt, runs spaCy named-entity recognition (NER)
                              on every article and writes
                                (:Topic)-[:HAS_DOCUMENT]->(:Document)-[:MENTIONS_<TYPE>]->(:Person|Organization|
                                Location|Date|Money|Number|NatReligPolitGroup|WorkOfArt)
  Pass 2  BBCKeywordImporter  re-reads the Documents from Neo4j, runs PyTextRank (a TextRank implementation
                              running as a spaCy pipeline component) to extract the top key-phrases and writes
                                (:Document)-[:MENTIONS_KEYWORD {rank}]->(:Keyword)

Resulting graph is the input of steps 2-3 (Wikidata enrichment) and of the Cypher listings in ../listings
(keyword similarity -> Louvain communities -> topics).

Connection settings (bolt URI, user, password) are resolved by util/graphdb_base.py in this order:
CLI options (-b, -u, -p) > NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD env vars > ../../config.ini.
The Docker setup uses the env vars. Re-running is safe: all writes use MERGE.

Must be run from the chapter folder with PYTHONPATH pointing at the repository root, because it imports
`util.*` and uses paths relative to the working directory (see the Makefile / Dockerfile).
"""
import sys
from pathlib import Path

import spacy
import pytextrank
from neo4j.exceptions import ClientError as Neo4jClientError

from util.base_importer import BaseImporter


class BBCImporter(BaseImporter):
    """Pass 1: documents + named entities."""

    def __init__(self, argv):
        super().__init__(command=__file__, argv=argv)
        #self._database = "news"

        # Load the small English spaCy pipeline (tokenizer, tagger, parser, NER). Installed separately with
        # `python -m spacy download en_core_web_sm` (done by `make init` / the Dockerfile).
        # Entity labels used later in the Cypher import query:
        #  NORP entity = Nationalities or religious or political groups
        #  FAC entity = Buildings, airports, highways, bridges etc.
        #  GPE entity = Countries, cities, states
        self.nlp = spacy.load("en_core_web_sm")

        # Optional: use a dedicated database instead of the default `neo4j` (needs Neo4j Enterprise):
        #   CREATE DATABASE news   and uncomment the `self._database = "news"` line above.
        # Create the uniqueness constraints up front, so MERGE below is fast and never duplicates nodes.
        self.create_indices()

    def create_indices(self):
        """
        Create one uniqueness constraint per node label. Besides data integrity this also creates the
        backing index, which is what makes the MERGE (match-or-create) statements in the import query
        efficient. `IF NOT EXISTS` makes the statement idempotent on Neo4j 4.4+/5.
        """
        with self._driver.session(database=self._database) as session:
            query = """
            CREATE CONSTRAINT doc_id_unique IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE;
            CREATE CONSTRAINT person_name_unique IF NOT EXISTS FOR (n:Person) REQUIRE n.name IS UNIQUE;
            CREATE CONSTRAINT location_name_unique IF NOT EXISTS FOR (n:Location) REQUIRE n.name IS UNIQUE;
            CREATE CONSTRAINT organization_name_unique IF NOT EXISTS FOR (n:Organization) REQUIRE n.name IS UNIQUE;
            CREATE CONSTRAINT date_name_unique IF NOT EXISTS FOR (n:Date) REQUIRE n.name IS UNIQUE;
            CREATE CONSTRAINT money_name_unique IF NOT EXISTS FOR (n:Money) REQUIRE n.name IS UNIQUE;
            CREATE CONSTRAINT number_name_unique IF NOT EXISTS FOR (n:Number) REQUIRE n.name IS UNIQUE;
            CREATE CONSTRAINT group_name_unique IF NOT EXISTS FOR (n:NatReligPolitGroup) REQUIRE n.name IS UNIQUE;
            CREATE CONSTRAINT workofart_name_unique IF NOT EXISTS FOR (n:WorkOfArt) REQUIRE n.name IS UNIQUE;
            CREATE CONSTRAINT keyword_name_unique IF NOT EXISTS FOR (n:Keyword) REQUIRE n.name IS UNIQUE"""
            # the driver runs one statement per call, so split the multi-statement string on ';'
            for q in query.split(";"):
                try:
                    session.run(q)
                except Neo4jClientError as e:
                    # ignore if we already have the rule in place
                    if e.code != "Neo.ClientError.Schema.EquivalentSchemaRuleAlreadyExists":
                        raise e

    @staticmethod
    def cleanse_entity(en: str):
        """
        Normalise an entity string so that surface variants collapse into a single node, e.g.
        "the BBC" -> "BBC", "Microsoft's" -> "Microsoft".
        (The unique constraint on `name` then merges them.)
        """
        TO_IGNORE = ["the", "a"]
        tokenized = en.split()
        if tokenized[0].lower() in TO_IGNORE:
            en = en[len(tokenized[0]):]
        en = en.replace("\'s", "")
        return en.strip()

    @staticmethod
    def count_documents(data_path: Path):
        """Number of article files (data/bbc/<topic>/*.txt); only used for the progress bar total."""
        return sum(1 for _ in data_path.glob("*/*.txt"))

    def get_documents(self, data_path: Path):
        """
        Generator yielding one dict per article, already enriched with entities:
            {"topic": "business", "id": "business_173", "title": ..., "text": ..., "PERSON": [...], "ORG": [...], ...}
        It is a generator so the whole corpus is never held in memory; batch_store() pulls from it in
        batches of `self.batch_size`.
        """
        for file in data_path.glob("*/*.txt"):
            # the folder name is the BBC category (business, entertainment, politics, sport, tech);
            # file: xyz/topic1/123.txt => id: topic1_123 (this id is also used by the Cypher listings, e.g. business_173)
            id_ = f"{file.parent.name}_{file.name[:-4]}"
            with file.open('r') as f:
                try:
                    # drop empty lines; first line is the headline, the remainder is the article body
                    lines = [x.strip() for x in f if len(x.strip()) > 1]
                    document = {"topic": file.parent.name, "id": id_, "title": lines[0],
                                "text": "\n".join(lines[1:])}
                    self.enrich_document(document)
                    yield document
                except UnicodeDecodeError:
                    # a few files are not valid UTF-8: skip them (note: prints the builtin `id`, not the document id)
                    print(f"UnicodeDecodeError for {id}")

    def enrich_document(self, document: dict):
        """
        Run spaCy NER on title + text and attach the result to `document` in place, grouped by spaCy label:
        document["ORG"] = ["BBC", "Microsoft", ...], document["GPE"] = [...], and so on.
        Duplicates are kept here; MERGE in Cypher makes the relationships unique per (document, entity).
        """
        processed = self.nlp(document['title'] + ".\n\n" + document['text'])
        for en in processed.ents:
            if en.label_ not in document:
                document[en.label_] = list()
            document[en.label_].append(self.cleanse_entity(en.text))

    def import_documents(self, data_path: Path):
        # One parametrised query, executed once per batch of 50 documents. UNWIND $batch iterates the batch;
        # MERGE = "find or create", so the import is idempotent. Each FOREACH maps one spaCy label to one
        # node label + relationship type. FOREACH over a missing key (e.g. an article without MONEY
        # entities) is a no-op because iterating null does nothing.
        #   PERSON -> Person, ORG -> Organization, GPE -> Location (countries/cities/states),
        #   DATE -> Date (lower-cased), MONEY -> Money, CARDINAL -> Number,
        #   NORP -> NatReligPolitGroup, WORK_OF_ART -> WorkOfArt
        # (the relationship name MENTIONS_NUMER is misspelled in the original book code; kept for compatibility
        # with the book's queries)
        import_document_query = """
        UNWIND $batch as item
        MERGE (t:Topic {name: item.topic})
        
        WITH item,t
        MERGE (n:Document {id: item.id}) 
        SET n.title = item.title, n.text = item.text
        MERGE (t)-[:HAS_DOCUMENT]->(n)
        
        WITH item,t,n
        FOREACH(entity IN item.PERSON |
              MERGE (e:Person {name: entity})
              MERGE (n)-[:MENTIONS_PERSON]->(e)
            )

            FOREACH(entity IN item.ORG |
              MERGE (e:Organization {name: entity})
              MERGE (n)-[:MENTIONS_ORGANIZATION]->(e)
            )

            FOREACH(entity IN item.GPE |
              MERGE (e:Location {name: entity})
              MERGE (n)-[:MENTIONS_LOCATION]->(e)
            )

            FOREACH(entity IN item.DATE |
              MERGE (e:Date {name: toLower(entity)})
              MERGE (n)-[:MENTIONS_DATE]->(e)
            )

            FOREACH(entity IN item.MONEY |
              MERGE (e:Money {name: entity})
              MERGE (n)-[:MENTIONS_MONEY]->(e)
            )

            FOREACH(entity IN item.CARDINAL |
              MERGE (e:Number {name: entity})
              MERGE (n)-[:MENTIONS_NUMER]->(e)
            )

            FOREACH(entity IN item.NORP |
              MERGE (e:NatReligPolitGroup {name: entity})
              MERGE (n)-[:MENTIONS_GROUP]->(e)
            )

            FOREACH(entity IN item.WORK_OF_ART |
              MERGE (e:WorkOfArt {name: entity})
              MERGE (n)-[:MENTIONS_WORK_OF_ART]->(e)
            )
        """
        # spaCy processing is the slow part (it happens lazily inside the get_documents generator),
        # so the tqdm progress bar here mostly reflects NER speed.
        size = self.count_documents(data_path)
        print(f"Importing {size} documents from {data_path}...")
        self.batch_size = 50
        self.batch_store(import_document_query, self.get_documents(data_path), size=size, desc="importing documents")


class BBCKeywordImporter(BaseImporter):
    """Pass 2: key-phrase extraction (reads the Documents back from Neo4j, writes Keyword nodes)."""

    def __init__(self, argv):
        super().__init__(command=__file__, argv=argv)
        #self._database = "news"
        self.nlp = spacy.load("en_core_web_sm")
        # Add PyTextRank to the spaCy pipeline. TextRank builds a word co-occurrence graph per document and
        # ranks phrases with PageRank; results are exposed as `doc._.phrases` (text + rank).
        self.nlp.add_pipe("textrank")

    @staticmethod
    def cleanse_keyword(kw: str):
        """Lower-case and strip leading determiners/possessives so "The Government" and "government" merge."""
        TO_IGNORE = ["the", "their", "a"]
        tokenized = kw.split()
        if tokenized[0].lower() in TO_IGNORE:
            kw = kw[len(tokenized[0]):]
        return kw.lower().strip()

    def count_documents(self):
        # only used for the progress bar
        count_query = "MATCH (n:Document) RETURN count(n) as total"
        with self._driver.session(database=self._database) as session:
            return session.run(count_query).single()["total"]

    def get_documents(self):
        """
        Stream every Document out of Neo4j and yield {"id": <internal node id>, "title", "text", "keywords"}.
        Keeps the 30 best-ranked phrases per document (single characters are dropped).
        The internal id(n) is used to find the node again when writing back.
        """
        query_documents = """
        MATCH (n:Document)
        RETURN id(n) AS id, n.title AS title, n.text AS text
        """
        with self._driver.session(database=self._database) as session:
            for document in session.run(query_documents):
                document = dict(document)
                processed = self.nlp(document['title'] + ".\n\n" + document['text'])
                document['keywords'] = [{'name': self.cleanse_keyword(x.text), 'rank': x.rank}
                                        for x in processed._.phrases
                                        if len(x.text) > 1][:30]
                yield document

    def import_keyword(self):
        # For each document create/reuse a Keyword node and link them. The TextRank score is kept on the
        # relationship (r.rank) because the same keyword has a different importance in each document.
        # Later listings (5a.11, 5a.16) use these links to compute document similarity and community terms.
        query_store_keywords = """
        UNWIND $batch AS item
        MATCH (n:Document)
        WHERE id(n) = item.id
        FOREACH(entity IN item.keywords |
            MERGE (e:Keyword {name: entity.name})
            MERGE (n)-[r:MENTIONS_KEYWORD]->(e)
            SET r.rank = entity.rank
        )"""
        size = self.count_documents()
        self.batch_size = 50
        self.batch_store(query_store_keywords, self.get_documents(), size=size, desc="importing keywords")


if __name__ == "__main__":
    # Entry point: `python importer/step1__import_bbc.py [-s <dataset dir>] [-b bolt://...] [-u user] [-p password]`
    importer = BBCImporter(argv=sys.argv[1:])
    base_path = importer.source_dataset_path

    if not base_path:
        print("source path directory is mandatory. Setting it to default.")
        base_path = "../../data/bbc/"

    base_path = Path(base_path)

    # Pass 1: ingest articles & run NER (writes Topic/Document/entity nodes)
    importer.import_documents(base_path)

    # Pass 2 must run after pass 1 because it reads the Document nodes created there.
    importerKW = BBCKeywordImporter(argv=sys.argv[1:])
    # for each article, extract keywords and key-phrases (enrichment of the KG created in previous step)
    importerKW.import_keyword()
