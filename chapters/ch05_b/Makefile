.PHONY: build up down run exec shell

build:
	docker compose build

up:
	docker compose up -d --build

down:
	docker compose down

# one-shot run in a throwaway container
run:
	docker compose run --rm extract

# run in the long-lived container started by `make up`
exec:
	docker compose exec workbench python "5b.3 - OpenAI extraction runner.py"

shell:
	docker compose exec workbench bash
