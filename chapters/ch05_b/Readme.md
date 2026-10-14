# Chapter 5: extracting domain-specific knowledge from unstructured data

This chapter turns free text into knowledge-graph triples with named entity recognition (NER) and relation
extraction. The `listings/` folder holds two approaches: an annotation API (UBIAI) and prompt-based extraction with
an OpenAI model. Nothing here writes to Neo4j. The output is a list of relations that can be loaded into a graph.
The book chapter is in [context/extracting-domain-knowledge-from-unstructured-data.pdf](context/extracting-domain-knowledge-from-unstructured-data.pdf).

## Getting started

`listing_3.py` reads `OPENAI_API_KEY` from the environment or from a `.env` file. It calls the OpenAI API with the
model `gpt-4o-mini`, so it needs internet access and spends tokens. Every run sends the diary text to OpenAI.

### With Docker (recommended)

The folder ships a [Dockerfile](Dockerfile) (`python:3.12-slim` plus `requirements.txt`), a
[docker-compose.yml](docker-compose.yml) and a [Makefile](Makefile).

```shell
cp .env.example .env        # then set OPENAI_API_KEY=sk-... in .env
make up                     # build the image and start the long-lived container
make exec                   # run listing_3.py (baseline prompt, listing 2) in it
make shell                  # bash inside the container
make run                    # alternative: one-shot run in a throwaway container
make down                   # stop and remove the stack
```

The compose project is called `ch05_b` and has two services built from the same image (`ch05_b-extract`):

| Service | What it is |
|---------|-----------|
| `workbench` | Long-lived container (`sleep infinity`, container name `ch05_b-workbench`). You run the listings in it with `docker compose exec`. It shows up under Containers in Docker Desktop. |
| `extract` | One-shot service for `docker compose run --rm extract`. It has the profile `run`, so `up` does not start it. |

`listings/` is mounted into the container, so edits on the host take effect without rebuilding. The API key is passed
through `.env` at run time and is not baked into the image. `.env` is git-ignored (see the root `.gitignore`) and
excluded from the build context by [.dockerignore](.dockerignore).

#### Where the output goes

The Logs tab of a container shows only the output of its main process (PID 1). In `workbench` that is
`sleep infinity`, so the Logs tab is empty and `docker compose exec` prints to your terminal instead. To have the
output in the container log as well, redirect it into PID 1's stdout:

```shell
docker compose exec workbench sh -c 'python listing_3.py > /proc/1/fd/1 2>&1'
docker compose logs workbench
```

#### Running listings 5 and 7 without editing `listing_3.py`

`listing_3.py` imports its prompt from `listing_2`. These commands swap the import on the fly in a temporary copy:

```shell
# listing 5
docker compose exec workbench sh -c \
  "sed 's/^from listing_2 import/from listing_5 import/' listing_3.py > /tmp/run5.py && PYTHONPATH=/app/listings python /tmp/run5.py"

# listing 7
docker compose exec workbench sh -c \
  "sed 's/^from listing_2 import/from listing_7 import/' listing_3.py > /tmp/run7.py && PYTHONPATH=/app/listings python /tmp/run7.py"
```

To run all three and compare, save each output to a file on the host:

```shell
for n in 2 5 7; do
  docker compose exec -T workbench sh -c \
    "sed 's/^from listing_2 import/from listing_$n import/' listing_3.py > /tmp/run$n.py && PYTHONPATH=/app/listings python /tmp/run$n.py" > out_$n.txt
done
diff out_5.txt out_7.txt
```

### Without Docker

Install the requirements (`openai`, `dotenv`, `requests`) into a virtual environment:
```shell
pip install -r requirements.txt
echo "OPENAI_API_KEY=<your key>" > .env
cd listings
python listing_3.py
```

To switch the prompt, change the import at the top of `listing_3.py`:
```python
from listing_2 import prompt_segments
#from listing_5 import prompt_segments
#from listing_7 import prompt_segments
```

## The listings in detail

The numbering skips 4 and 6, because those listings in the book are not code files.

### listing_1.py: the UBIAI annotation API

This is the "annotation service" approach to NER and relation extraction. The script:

- POSTs `{"inputs": [text, ...]}` as JSON to `https://api.ubiai.tools:8443/api_v1/annotate/<token>`. The API token is part
  of the URL path.
- Decodes the response body as UTF-8 and parses it into `res`.
- Does nothing with `res`. It never prints or uses it. The book text around the listing explains the response format.

`my_token = "XXX"` and the `<put your text here>` strings are placeholders, so the script cannot run as is. It needs
a UBIAI account and has nothing to do with OpenAI or with listings 2 to 7.

### listing_2.py: the baseline prompt

Defines a `prompt_segments` dictionary with three keys:

- `task` is the system message. It says the model is an expert at building knowledge graphs from texts with NER and
  relation extraction. It asks for "as many entities and relations among them as possible" in the format
  `[ENTITY 1, ENTITY 1 TYPE, RELATION, ENTITY 2, ENTITY 2 TYPE]` and states that the relations are directed, so the
  order matters.
- `example` is the one-shot user turn: "J.R.Smith (Prof. Phys.) is employed by MIT and mentioned another scientist,
  Mary Hodge, who works on cyclotron research."
- `example_output` is the matching assistant turn, four relations: `has title`, `works for`, `talked about`,
  `works on`.

The model is told only the output format. It chooses the entity types and relations itself.

### listing_3.py: the runner

The only file with a `__main__` block. It:

- Loads `.env` with `load_dotenv()` and reads `OPENAI_API_KEY`. The model is `gpt-4o-mini`.
- Builds one chat from `prompt_segments`: `task` as the system message, `example` and `example_output` as a fake
  user/assistant pair, then the real text as the last user message.
- Calls the API with `temperature=0` and `max_tokens=2000`, prints the reply and the elapsed time, and returns the reply.
  Temperature 0 makes the output close to deterministic, but not fully (see [Variability](#variability)).
- Uses a 1932 diary entry by Warren Weaver about the Johns Hopkins chemistry department as the sample text. It is full
  of abbreviations: "WW", "Dept.", "Prof. Chem.", "D.H. Andrews", "Assoc. in Chem.".

### listing_5.py: the prompt with a schema

Same output format and the same one-shot example as listing 2. Only `task` changes. It adds:

- Entity types of interest: person, location, organization, date, occupation. "Occupation" is a broad bucket for a
  person's work, specialization, research discipline, interests, occupation and technology.
- Relations of interest: `works for`, `works with`, `student of` (links students with their teachers or advisors),
  `talked about` (a person talking about another person), `talked with` (a person talking with another person),
  `works on` (assigns persons to their work, specialization, research discipline, interests).
- Abbreviation hints. People are first named in full and later shortened ("A. N. Richards" becomes "Richards",
  "ANR" or "R."). Organizations are shortened too ("University of California" becomes "U. of Cal." or "U. Cal.",
  "Department of Physics" becomes "Dept. Phys.").

### listing_7.py: the domain-specific prompt

Builds on listing 5 with two changes:

- The task states the domain: the text is "a diary entry of Warren Weaver (often referred to as WW)". The `works on`
  gloss now also mentions technology.
- The one-shot example is richer: Mary Hodge is a colleague at MIT who studies radioisotopes produced by a cyclotron
  together with her master's student John Smith. The example output has seven relations instead of four, including
  `student of` and a second person who `works for` MIT, and it uses the full name "Mary Hodge" consistently.

## How the prompt, the schema and the example change from listing 2 to 7

Each prompt has a `task` (instructions), and an `example` plus `example_output` (one worked demonstration).

### The task

| Element | Listing 2 | Listing 5 | Listing 7 |
|---------|-----------|-----------|-----------|
| Role: expert in knowledge graphs, NER and relation extraction | yes | yes | yes |
| Goal: as many entities and relations as possible | yes | yes | yes |
| Output format `[E1, E1 TYPE, RELATION, E2, E2 TYPE]`, directed | yes | yes | yes |
| What the text is | "a prompt" | "a prompt" | a diary entry of Warren Weaver (WW) |
| Schema (entity types and relations) | none | yes | yes (same lists, `works on` gloss extended) |
| Abbreviation hints | none | yes | yes |

The first three rows never change, so all three produce the same line format and one parser reads all the outputs.

### The schema

- **Listing 2** has no schema. The model picks the types and relations, which gives entity types like `field`,
  `research`, `event` and `department`, and one-off verbs like `is not present at` or `prepared`.
- **Listing 5** adds the schema. This narrows the types and brings in schema relations (`works on`, `talked with`).
  The schema is a request, not a rule: the model still invents relations (`measures`, `demonstrates`, `impresses as`)
  and puts everything that is not a person or organization into the broad `occupation` type.
- **Listing 7** keeps the schema and adds the domain and a better example. The schema relations dominate the output.

### The abbreviation hints

They appear from listing 5 on. They matter because the diary is full of short forms. They help only partly: listing 5
still produces "Dept. Chem." as an organization next to "Chemistry Department". In listing 7 the department appears
under one name.

### The domain context

Only listing 7 says whose diary it is. Before, "WW" was an unexplained token. Now it is the diary's author, the subject
of `visited` and `talked with`.

### The one-shot example

| | Listings 2 and 5 (identical) | Listing 7 |
|---|---|---|
| Input | J.R.Smith, MIT, Mary Hodge, cyclotron research | J.R.Smith, MIT, Mary Hodge, her master's student John Smith, radioisotopes from a cyclotron |
| People | 2 | 3 |
| Output lines | 4 | 7 |
| Relations shown | `has title`, `works for`, `talked about`, `works on` | the same four, plus `student of` and a second `works for` |
| Naming | "Mary" | "Mary Hodge", used consistently |

The example is the strongest signal. The model imitates what it is shown more reliably than it follows a list in the
task. Listing 7's output uses `student of` for Mayer and Lewis, which the other two prompts do not.

### Summary of the progression

1. **Listing 2** defines the output format. The model decides which entity types and relations matter.
2. **Listing 5** adds the schema and the abbreviation hints. The relations become more consistent and easier to map to
   graph labels and relationship types.
3. **Listing 7** adds domain context and a richer example. This helps with the abbreviated names and with resolving
   "WW" to a person.

The output format is the same in all three, so every result can be parsed into `(source)-[relation]->(target)` rows
with node labels taken from the two entity types.

## Reading the output

Each output line is one directed relation:

```
["D.H. Andrews", "person", "specializes in", "thermodynamics", "field"]
 entity 1        type 1     relation          entity 2          type 2
```

In a graph this becomes `(:person {name: "D.H. Andrews"})-[:SPECIALIZES_IN]->(:field {name: "thermodynamics"})`.
The last two lines of a run (`Time: ... sec` and a row of dashes) are printed by the script, not by the model.

## Comparison of listings 2, 5 and 7 on the diary text

One run per prompt, `gpt-4o-mini`, `temperature=0`, same text.

| | Listing 2 | Listing 5 | Listing 7 |
|---|---|---|---|
| Relations | 17 | 20 | 19 |
| Entity types used | 8: person, organization, title, field, research, event, department, publication | 6: person, organization, location, date, title, occupation | 5: person, organization, location, title, occupation |
| Schema relations used | `works for`, `works with` | `works with`, `talked with`, `talked about`, `works on` | all six; 11 of the 19 lines |
| Time | 8.0 s | 5.8 s | 6.7 s |

What stands out:

- **Listing 2** has free-form types and verbs: `field`, `research`, `event`, `is not present at`, `prepared`. It is the
  only one that kept Born's treatise and the new edition.
- **Listing 5** stays mostly within the allowed entity types, but everything else is pushed into `occupation`
  (even "enthusiastic and able man"). Relations are still partly free-form (`measures`, `demonstrates`,
  `impresses as`, `is not present at`). "Dept. Chem." and "Chemistry Department" are separate organizations.
- **Listing 7** follows the schema best: `student of` for Mayer and Lewis, `works for` for the people at Hopkins,
  `works on` for the research, and one name for the department. Only `has title`, `works at`, `works in` and
  `is wife of` are off-schema.

Errors to watch for:

- Listing 5: `D. H. Andrews impresses as enthusiastic and able man` has the wrong subject (the text says Mayer). The
  date line `Wednesday, November 9, 1932 is the date of WW` is a weak edge. Frazer's `works for` is missing.
- Listing 7: `Dr. Frazer talked about D. H. Andrews` is not supported by the text. The `works for` lines for Andrews
  and Mayer are inferred from the context, which is reasonable but not stated. The Raman spectra and Born's treatise
  are dropped.
- All three: `has title` and similar descriptive edges point to a literal value and are better stored as node
  properties. "the mathematician" (Mrs. Wintner's husband) is a node without a name.

Overall, listing 7 gives the cleanest set for building a graph, at the cost of dropping some details and adding the
odd unsupported edge, so the extracted relations still need a review step before loading.

### Variability

`temperature=0` makes the output more stable, but it is not fully deterministic. Two runs of the baseline prompt on
the same text differed: one had `Max Born is at Gottingen`, `Andrews says that Mayer` and `impresses as`, the other had
`Max Born is the author of Born's treatise` and `Mrs. Wintner prepared the new edition`. A single run is therefore not
a reliable benchmark. When you compare prompts, run each a few times and compare the structure (types, relations used),
not exact lines.
