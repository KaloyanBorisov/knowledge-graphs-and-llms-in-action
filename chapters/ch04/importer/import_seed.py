import sys

from util.graphdb_base import GraphDBBase

if __name__ == '__main__':
    importing = GraphDBBase(argv=sys.argv[1:])

    with importing._driver.session() as session:
        # Listing 4.6: restore the PPI database from a Neo4j backup.
        # The seed provider is enabled by the compose env var
        # NEO4J_dbms_databases_seed__from__uri__providers.
        print("importing PPI")
        ppi_uri = "https://downloads.graphaware.com/neo4j-db-seeds/ppi-5.26.4-2025-03-22T08-30-33.backup"
        result = session.run(f"""
            CREATE DATABASE ppi IF NOT EXISTS OPTIONS {{ existingData: "use", seedUri: "{ppi_uri}" }}
        """)
        print("system updates:", result.consume().counters.system_updates)
        # the restore runs in the background; prepare_gds.sh waits for it to come online
        for r in session.run("SHOW DATABASE ppi YIELD currentStatus, statusMessage"):
            print("ppi status:", r["currentStatus"], r["statusMessage"])
    importing.close()
