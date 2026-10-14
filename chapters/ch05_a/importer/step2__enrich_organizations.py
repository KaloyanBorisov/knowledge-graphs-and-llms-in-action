"""
Step 2 - enrich Organization nodes with facts from Wikidata.

Entity linking by name: for every Organization mentioned in more than 4 documents (frequent ones only,
to limit the number of API calls) we ask the Wikidata SPARQL endpoint for an entity whose English label
equals the organization name and which is a business/organization. We store on the node:
    description, wikidata_id, wikidata_url
and create
    (org)-[:HAS_SUBSIDIARY]->(:Organization)   Wikidata P355
    (org)-[:MEMBER_OF]->(:Organization)        Wikidata P463
    (org)-[:IN_INDUSTRY]->(:Industry)          Wikidata P452
The wikidata_id set here is what step 3 uses to look up owners.

Network traffic is minimised by a file cache: every SPARQL response is saved as
data/cache_org/<entity_name>.json and re-used on later runs (the repo ships with these files, so a normal
run makes few or no real HTTP calls). Delete a file to force a refresh.
"""
import sys
import json
import time
from pathlib import Path

import requests

from util.base_importer import BaseImporter
from tenacity import retry, wait_exponential, stop_after_attempt


# tenacity retry: up to 10 attempts with exponential back-off (1s .. 10s) whenever the function raises.
# Caveat: every exception, including the 429 RuntimeError, is caught inside the function and converted to an
# empty result, so the decorator never actually sees a failure and retries never trigger. Kept as in the book.
@retry(stop=stop_after_attempt(10), wait=wait_exponential(multiplier=1, min=1, max=10))
def query_wikidata_entity(query: str, entity: str, cache_folder: Path = None):
    """
    Run a SPARQL query against Wikidata, with an on-disk cache.
    :param query: SPARQL template containing a single `%s` placeholder
    :param entity: value substituted into the placeholder (an organization name, a Wikidata id, ...);
                   also used as the cache file name
    :param cache_folder: directory for cached JSON responses; caching is skipped when None or not a directory
    :return: list of SPARQL result bindings (dicts), or an empty dict on error / no match
    """

    # cache check: "Bank of America"  => /cache_folder/bank_of_america.json
    # (caveat: names containing '/' would produce an invalid path; the cache is keyed by name only)
    filename = entity.replace(" ", "_").lower() + ".json"
    if cache_folder is not None and cache_folder.is_dir():
        if (cache_folder / filename).exists():
            results = json.load((cache_folder / filename).open())
            return results

    # cache miss, issuing the request. The query text is interpolated into the URL, `format=json` asks for
    # the standard SPARQL JSON result format.
    try:
        URL = f"https://query.wikidata.org/bigdata/namespace/wdq/sparql?query={query % entity}"
        response = requests.get(URL, params={'format': "json"})
        if response.status_code == 429:
            # rate limited by the public endpoint: raising here lets the @retry decorator back off and try again
            raise RuntimeError("Too many requests")
        time.sleep(1)  # wait a second to avoid "Too Many Requests" errors (throttle after every real request).
        # Wikidata's response is {"head": ..., "results": {"bindings": [ {var: {"value": ...}}, ... ]}}
        parsed = json.loads(response.content)
    except json.decoder.JSONDecodeError as e:
        print(f"JSONDecodeError: Couldn't process entity {entity}: {e}")
        return dict()
    except Exception as e:
        print(f"Couldn't process entity {entity}: {e}")
        return dict()
    results = parsed['results']['bindings']

    # cache the response (also caches empty results, so unknown entities are not asked for twice)
    if cache_folder is not None and cache_folder.is_dir():
        json.dump(results, (cache_folder / filename).open("w"))
    return results


class OrgEnricher(BaseImporter):
    """Reads frequent Organization nodes from Neo4j, looks them up in Wikidata, writes the facts back."""

    def __init__(self, argv):
        super().__init__(command=__file__, argv=argv)
        #self._database = "news"
        self.cachePath = None

        # Inputs: organizations mentioned by more than 4 documents (c > 4). Returns the internal node id so the
        # result can be written back to exactly that node.
        self.QUERY_GET_INPUTS = """
        MATCH (n:Document)-[:MENTIONS_ORGANIZATION]->(e:Organization)
        WITH e, count(*) AS c
        WHERE c > 4
        RETURN id(e) AS id, e.name AS name
        """

        # Output: set the scalar properties on the node, then create related nodes from the lists.
        # `$input` is the dict built in get_wikidata() (+ the node id added in run()).
        self.QUERY_STORE_RESULTS = """
        MATCH (n)
        WHERE id(n) = $input.id
        SET n.description = $input.description,
        n.wikidata_id = $input.wikidata_id,
        n.wikidata_url = $input.wikidata_url
    
        WITH n 
    
        FOREACH(entity IN $input.subsidiary |
            MERGE (e:Organization {name: entity})
            MERGE (n)-[:HAS_SUBSIDIARY]->(e)
        )
    
        FOREACH(entity IN $input.member_of |
            MERGE (e:Organization {name: entity})
            MERGE (n)-[:MEMBER_OF]->(e)
        )
    
        FOREACH(entity IN $input.industry |
            MERGE (e:Industry {name: entity})
            MERGE (n)-[:IN_INDUSTRY]->(e)
        )
        """

    def get_wikidata(self, entity: str):
        """
        Look up one organization by its exact English label.
        :return: {'name', 'wikidata_url', 'wikidata_id', 'description', 'subsidiary', 'member_of', 'industry'}
                 or an empty dict when Wikidata has no matching organization.
        If several entities share the label only the first result row is used (no disambiguation).
        """
        # Query logic:
        #  - ?org is an instance (P31) of "business" (Q4830453) or of "organization" (Q43229), including
        #    subclasses (P279*), and has the English label we are looking for (%s is replaced by the name);
        #  - it must have an English description;
        #  - OPTIONAL clauses fetch country (P17), subsidiary (P355), industry (P452), short name (P1813)
        #    and memberships (P463) when available;
        #  - group_concat collapses multiple values into one ';'-separated string per organization, which is
        #    split again in Python below. The label SERVICE resolves the *Label variables.
        SPARQL = """
        SELECT ?org ?orgLabel ?desc  
               (group_concat(distinct ?subsidiaryLabel;separator=";") as ?subsidiaries)  
               (group_concat(distinct ?member_ofLabel;separator=";") as ?members)  
               (group_concat(distinct ?industryLabel;separator=";") as $industries)
        WHERE {{?org wdt:P31/wdt:P279* wd:Q4830453 .}
         UNION
         {?org     wdt:P31/wdt:P279*  wd:Q43229 .}
         ?org      rdfs:label '%s'@en .
         ?org schema:description ?desc .
         OPTIONAL {?org        wdt:P17 ?country . }
         OPTIONAL {?org        wdt:P355 ?subsidiary . }
         OPTIONAL {?org        wdt:P452 ?industry . }
         OPTIONAL {?org        wdt:P1813 ?short_name . }
         OPTIONAL {?org        wdt:P463 ?member_of . }
         FILTER(LANG(?desc) = "en")
         SERVICE wikibase:label { 
           bd:serviceParam wikibase:language "en".
           ?org rdfs:label ?orgLabel.
           ?subsidiary rdfs:label ?subsidiaryLabel.
           ?industry rdfs:label ?industryLabel.
           ?member_of rdfs:label ?member_ofLabel.
         }
        }
        GROUP BY ?org ?orgLabel ?desc
        """

        # cache folder is relative to the working directory (chapters/ch05_a -> <repo>/data/cache_org)
        results = query_wikidata_entity(SPARQL, entity, Path("../../data/cache_org"))

        # Flatten the first binding into a plain dict; set() removes duplicate values, and an organization
        # without e.g. subsidiaries yields [''] (empty string) from split(), which becomes a node named ''.
        final_res = {'name': results[0]['orgLabel']['value'],
                     'wikidata_url': results[0]['org']['value'],
                     'wikidata_id': results[0]['org']['value'].split("/")[-1].strip(),
                     'description': results[0]['desc']['value'],
                     'subsidiary': list(set(results[0]['subsidiaries']['value'].split(";"))),
                     'member_of': list(set(results[0]['members']['value'].split(";"))),
                     'industry': list(set(results[0]['industries']['value'].split(";"))),
                     } if len(results) > 0 else dict()

        return final_res

    def run(self):
        """Fetch candidate organizations, enrich each one and store the result (one write per entity)."""
        # Run enrichment
        with self._driver.session(database=self._database) as session:
            # Get entities to enrich
            entities = session.run(self.QUERY_GET_INPUTS).data()
            print(f"Retrieved {len(entities)} entities")

            print("Retrieving wikidata info for entity:")
            for en in entities:
                print(en['name'])
                wiki = self.get_wikidata(en['name'])
                # time.sleep(1)  # to avoid exception about too many requests
                if len(wiki) == 0:
                    # no organization with this label in Wikidata: leave the node untouched
                    # print("  Nothing found.")
                    continue
                wiki['id'] = en['id']
                session.run(self.QUERY_STORE_RESULTS, input=wiki)
                print("  STORED!")


if __name__ == "__main__":
    # Entry point: run after step 1 (needs Organization nodes) and before step 3 (needs wikidata_id).
    enricher = OrgEnricher(argv=sys.argv[1:])

    # set up a cache folder for wikidata responses
    # (informational: the lookup itself uses the hard-coded path inside get_wikidata(); this just makes sure
    # the folder exists so responses can be written to it)
    enricher.cachePath = Path("../../data/cache_org")
    enricher.cachePath.mkdir(exist_ok=True)

    enricher.run()