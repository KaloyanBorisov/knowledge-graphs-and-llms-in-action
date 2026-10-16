"""
Step 3 - add ownership relationships between organizations (and their owners) using Wikidata.

For every Organization that step 2 linked to Wikidata (has a wikidata_id) we ask which entities own it
(Wikidata property P127 "owned by") and create
    (org)-[:OWNED_BY_ORG]->(:Organization:Owner)
    (org)-[:OWNED_BY_PER]->(:Person:Owner)
so that the graph can answer questions such as "which parent company stands behind the organizations
mentioned in this article?".

Responses are cached per Wikidata id in data/cache_owners/<id>.json (same mechanism as step 2).
Requires step 2 to have run, otherwise no Organization has a wikidata_id and nothing happens.
"""
import sys
import time
from pathlib import Path

import math
import spacy
from tqdm.auto import tqdm

from util.base_importer import BaseImporter
from step2__enrich_organizations import query_wikidata_entity


class OwnershipEnricher(BaseImporter):
    """Looks up owners of already-linked organizations in Wikidata and stores them as graph relationships."""

    def __init__(self, argv):
        super().__init__(command=__file__, argv=argv)
        #self._database = "news"
        self.cache_folder = None

        # Inputs: all organizations that step 2 successfully linked to Wikidata.
        self.QUERY_GET_INPUTS = """MATCH (e:Organization)
        WHERE e.wikidata_id IS NOT NULL
        RETURN id(e) AS id, e.name AS name, e.wikidata_id AS wikidata_id
        """

        # Output: one write for the whole list ($inputs). Owner nodes are MERGEd by name and given the extra
        # label :Owner so they can be found/filtered together regardless of being a Person or Organization.
        self.QUERY_STORE_RESULTS = """UNWIND $inputs AS input
        MATCH (n)
        WHERE id(n) = input.id
    
        FOREACH(entity IN input.owned_by_org |
            MERGE (e:Organization {name: entity})
            SET e:Owner
            MERGE (n)-[:OWNED_BY_ORG]->(e)
        )
    
        FOREACH(entity IN input.owned_by_per |
            MERGE (e:Person {name: entity})
            SET e:Owner
            MERGE (n)-[:OWNED_BY_PER]->(e)
        )
        """

    def get_onwers_with_type(self, entity):
        """
        Fetch the owners of one organization together with the owner's type, in a single query.
        :param entity: {"id": <node id>, "name": ..., "wikidata_id": "Q..."}
        :return: {'id', 'owned_by_org': [names], 'owned_by_per': [names]} or None if Wikidata lists no owner
        """
        # wd:%s is the organization's Wikidata id; ?owned_by is the owner (P127) and ?owner_instance_of its
        # type (P31). Q5 is "human", so type Q5 means the owner is a person, anything else an organization.
        SPARQL = """
        SELECT ?owned_by ?owned_byLabel ?owner_instance_of 
        WHERE {
          wd:%s wdt:P127 ?owned_by .
          ?owned_by wdt:P31 ?owner_instance_of .
          SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
        }"""
        results = query_wikidata_entity(SPARQL, entity["wikidata_id"], self.cache_folder)
        # Each result row is one (owner, type) pair, so an owner with several types appears several times.
        # Wikidata Q5 = "human": an owner with at least one Q5 row is a person, any other owner an organization.
        # (The original book code compared the binding dict to a string and had the branches swapped, which
        # put every owner into owned_by_per; fixed here.)
        person_labels = {}
        org_labels = {}
        for r in results:
            label = r["owned_byLabel"]["value"]
            if r["owner_instance_of"]["value"].endswith("/entity/Q5"):
                person_labels[label] = True
            else:
                org_labels[label] = True
        owned_by_per = list(person_labels)
        owned_by_org = [x for x in org_labels if x not in person_labels]
        if len(results) > 0:
            # result shape matches what QUERY_STORE_RESULTS expects
            return {'id': entity["id"],
                    'owned_by_org': owned_by_org,
                    'owned_by_per': owned_by_per}
        # implicit return None when there is no owner; run() filters those out
        pass

    # ---------------------------------------------------------------------------------------------
    # get_owners() and disambiguate_owners() are an alternative, batched implementation (one SPARQL call
    # for many entities, then a second call to classify the owners). They are only reachable from the dead
    # code after `return` in run() and are kept as a reference.
    # ---------------------------------------------------------------------------------------------
    @staticmethod
    def get_owners(entities: list):
        """
        Retrieve wikidata IDs of owners for each entity
        :param entities: list of entities represented as dictionaries
        :return: dictionary {<entity_node_id>: list(owners)}
        """
        # build a SPARQL VALUES list: (wd:Q1) (wd:Q2) ...
        ents = " ".join([f"(wd:{x['wikidata_id']})" for x in entities])
        SPARQL = """
        SELECT ?org ?owned_by
        WHERE { VALUES(?org) {%s} .
                ?org wdt:P127 ?owned_by .
            SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
        }
        """

        results = query_wikidata_entity(SPARQL, ents)
        final_res = dict()
        for r in results:
            org_id = r['org']['value'].split("/")[-1].strip()
            node_id = [x['id'] for x in entities if x['wikidata_id'] == org_id][0]
            if node_id not in final_res:
                final_res[node_id] = list()
            final_res[node_id].append(r['owned_by']['value'].split("/")[-1].strip())

        return final_res

    @staticmethod
    def disambiguate_owners(entities: dict):
        """
        Second step of the batched alternative: classify every owner id as person (instance of Q5) or
        organization and resolve its label.
        :param entities: {node_id: [owner wikidata ids]} as returned by get_owners()
        :return: list of {'id', 'owned_by_org', 'owned_by_per'} ready for QUERY_STORE_RESULTS
        """
        # verify owner entity type (Organization or Person)
        ents = " ".join([f"(wd:{owner})" for x in entities.values() for owner in x])
        SPARQL = """
        SELECT ?ent ?entLabel ?instance_of
        WHERE {
            VALUES(?ent) {%s} .
            OPTIONAL {?ent wdt:P31 ?instance_of . }
            SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
        }
        """

        results = query_wikidata_entity(SPARQL, ents)

        dict_owners = dict()
        for r in results:
            ent = r['ent']['value'].split("/")[-1]
            inst = r['instance_of']['value'].split("/")[-1] if 'instance_of' in r else None
            dict_owners[ent] = {'name': r['entLabel']['value'].strip(),
                                'type': "person" if inst == "Q5" else "organization"
                                }

        final_res = list()
        for en, owners in entities.items():
            final_res.append({'id': en, 'owned_by_org': list(), 'owned_by_per': list()})
            for ow in owners:
                label = 'owned_by_per' if dict_owners[ow]['type'] == "person" else 'owned_by_org'
                final_res[-1][label].append(dict_owners[ow]['name'])

        return final_res

    def run(self):
        """Look up owners per organization (cached), then write all results to Neo4j in one query."""
        # Get entities to enrich
        with self._driver.session(database=self._database) as session:
            entities = session.run(self.QUERY_GET_INPUTS).data()
            print(f"Retrieved {len(entities)} entities")
            results = []
            for e in tqdm(entities[:], desc="acquiring owners"):
                res = self.get_onwers_with_type(entity=e)
                if res is not None:
                    results.append(res)
            session.run(self.QUERY_STORE_RESULTS, inputs=results)
            # The method ends here. Everything below is unreachable (kept from the book's earlier batched
            # variant that uses get_owners/disambiguate_owners; it also never used its `batch` variable).
            return

            # run in batches
            NUM_BATCHES = 20
            batches = spacy.util.minibatch(entities, NUM_BATCHES)
            print(f"Entities split into {math.ceil(1.0 * len(entities) / NUM_BATCHES)} batches")
            for idx, batch in enumerate(batches):
                print(f"Processing batch {idx}")
                owners = self.get_owners(entities)
                time.sleep(1)
                results = self.disambiguate_owners(owners)
                time.sleep(1)
                session.run(self.QUERY_STORE_RESULTS, inputs=results)


if __name__ == "__main__":
    # Entry point: run last, after steps 1 and 2.
    enricher = OwnershipEnricher(argv=sys.argv[1:])

    # set up a cache folder for wikidata responses
    enricher.cache_folder = Path("../../data/cache_owners")
    enricher.cache_folder.mkdir(exist_ok=True)

    enricher.run()
