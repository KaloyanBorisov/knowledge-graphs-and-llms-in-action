# Chapter 5: extracting domain-specific knowledge from unstructured data

This chapter turns free text into knowledge-graph triples with named entity recognition (NER) and relation
extraction. The `listings/` folder holds two approaches: an annotation API (UBIAI) and prompt-based extraction with
an OpenAI model. Nothing here writes to Neo4j. The output is a list of relations that can be loaded into a graph.
The book chapter is in [context/extracting-domain-knowledge-from-unstructured-data.pdf](context/extracting-domain-knowledge-from-unstructured-data.pdf).

## Getting started

Install the requirements (`openai`, `dotenv`, `requests`) into a virtual environment:
```shell
pip install -r requirements.txt
```

`listing_3.py` reads `OPENAI_API_KEY` from the environment or from a `.env` file in the working directory:
```shell
echo "OPENAI_API_KEY=<your key>" > .env
cd listings
python listing_3.py
```

It calls the OpenAI API with the model `gpt-4o-mini`, so it needs internet access and spends tokens.

## The listings

| File | What it does |
|------|--------------|
| [listing_1.py](listings/listing_1.py) | Sends a list of texts to the UBIAI annotation API (`/api_v1/annotate/`) and parses the JSON response. Put your own token in `my_token` and your texts in `inputs`. Not runnable as is: both are placeholders. |
| [listing_2.py](listings/listing_2.py) | Baseline prompt. The task is to find entities and relations and print them as `[ENTITY 1, ENTITY 1 TYPE, RELATION, ENTITY 2, ENTITY 2 TYPE]`. One worked example (the "J.R.Smith / MIT / Mary Hodge" sentence) is included as a one-shot demonstration. |
| [listing_3.py](listings/listing_3.py) | The runner. Builds a chat with the `task` as the system message, the `example` and `example_output` as a user/assistant pair, then the text to process. Uses `temperature=0` and `max_tokens=2000`, prints the extracted relations and the elapsed time. The sample text is a 1932 diary entry about the Johns Hopkins chemistry department. |
| [listing_5.py](listings/listing_5.py) | Refined prompt. Restricts the entity types (person, location, organization, date, occupation) and the relations of interest (`works for`, `works with`, `student of`, `talked about`, `talked with`, `works on`). Adds hints that people and organizations appear in shortened forms ("A. N. Richards" as "Richards" or "ANR", "Dept. Phys."). |
| [listing_7.py](listings/listing_7.py) | Domain-specific prompt. Same as listing 5, but the task states that the text is a diary entry of Warren Weaver (WW), and the one-shot example is richer: it also shows a `student of` relation and a person who `works for` an organization. |

Listings 2, 5 and 7 only define a `prompt_segments` dictionary with the keys `task`, `example` and `example_output`.
To compare them, switch the import at the top of `listing_3.py`:
```python
from listing_2 import prompt_segments
#from listing_5 import prompt_segments
#from listing_7 import prompt_segments
```

The numbering skips 4 and 6, because those listings in the book are not code files.

## How the prompt improves from 2 to 7

1. **Listing 2** only defines the output format. The model decides on its own which entity types and relations matter.
2. **Listing 5** adds the schema: which entity types and relations to extract, and how names are abbreviated.
   This gives more consistent relations that can be mapped to graph labels and relationship types.
3. **Listing 7** adds domain context (whose diary it is) and a richer example, which helps with the abbreviated
   names and with resolving "WW" to a person.

The output format is the same in all three, so every result can be parsed into `(source)-[relation]->(target)` rows
with node labels taken from the two entity types.
