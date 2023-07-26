DC = docker-compose
UID = $(shell id -u)

# Build docker images.
build:
	${DC} build --pull

# Docker cleaning.
clean:
	docker system prune -a -f --volumes

# Exec bash shell on django container.
shell:
	${DC} run --user ${UID} --rm web bash

# Run django shell on django container.
djshell:
	${DC} run --rm web django-admin shell

# Start project.
start:
	${DC} up --remove-orphans
