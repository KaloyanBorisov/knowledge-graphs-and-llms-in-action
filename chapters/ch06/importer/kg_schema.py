"""
kg_schema.py - static configuration of the knowledge graph (no logic, no DB access).

Everything that *defines* what the final KG looks like lives here, so the schema can
be changed without touching any of the pipeline code.

Used by:
    entity_normalization.normalize_entities  -> REMOVE_TITLES
    kg_builder.create_kg                      -> RENAME_ENTS, RENAME_RELS, SCHEMA
"""

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

# Honorifics / titles that the LLM sometimes includes as part of a *person name*
# (e.g. "Dr. Hale"). A name that STARTS WITH one of these (case-insensitive) has its
# first word removed when computing `name_normalized`.
REMOVE_TITLES = ["dr.", "prof.", "dean", "president", "pres.", "sir", "mr.", "mrs."]

# ---------------------------------------------------------------------------
# Final KG creation
# ---------------------------------------------------------------------------

# Entity labels produced by the LLM that must be mapped to a label of the final KG.
# (Technologies are treated as occupations/research areas.)
RENAME_ENTS = {'Technology': 'Occupation'}

# Different verbs the LLM used for "two people interacted" are all collapsed into
# one relationship type of the final KG.
RENAME_RELS = {'TALKED_TO': 'TALKED_WITH',
               'MET': 'TALKED_WITH',
               'TOOK_LUNCHEON_WITH': 'TALKED_WITH',
               'MENTIONED': 'TALKED_WITH',
               'MENTIONS': 'TALKED_WITH'
               }

# The ONLY (source label, relationship type, target label) triples that survive into
# the final KG. Anything the LLM extracted that is not listed here is discarded.
SCHEMA = [
    ['Person', 'WORKS_FOR', 'Organization'],
    ['Person', 'WORKS_ON', 'Occupation'],
    ['Person', 'HAS_TITLE', 'Title'],
    ['Person', 'TALKED_WITH', 'Person'],
    ['Person', 'TALKED_ABOUT', 'Person'],
    ['Person', 'STUDENT_OF', 'Person'],
    ['Person', 'WORKS_WITH', 'Person']
]
