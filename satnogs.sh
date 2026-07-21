#!/bin/sh -e
#
# Development and maintenance script
#
# Copyright (C) 2021, 2023 Libre Space Foundation <https://libre.space/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

if ! command -v docker-compose > /dev/null 2>&1
then
	COMPOSE_CMD="docker"
	COMPOSE_ARG="compose"
else
	COMPOSE_CMD="docker-compose"
fi

COMPOSE_FILE="docker-compose.yml"
SERVICE_WEB="web"
SHELL_CMD="/bin/bash"
REFRESH_CMD="./contrib/refresh-requirements.sh"
TOX_CMD="tox"
MANAGE_CMD="django-admin"
NPM_CMD="npm"
PYTHON_VERSION="3.9"

usage() {
	cat <<EOF
Usage: $(basename "$0") [OPTIONS]... [COMMAND]...
SatNOGS Development and Maintenance script.

DOCKER COMMANDS:
  up                    Start services in the background and attempt to
                         initialize the installation.
  shell SERVICE         Open a shell to a running service.
  clean                 Bring down all services and remove volumes.
  django-admin          Execute 'django-admin'. See 'django-admin help'
                         for available subcommands.
  compose DOCKER_COMPOSE_COMMANDS [ARGS]
                        Run any Docker Compose command.
                         See 'docker-compose --help' for details.

VIRTUALENV COMMANDS:
  develop               Run application in development mode and
                         initialize, if needed.
  develop_celery        Run Celery in development mode and initialize,
                         if needed.
  remove                Remove virtualenv.

DEVELOPMENT AND MAINTENANCE COMMANDS:
  tox [ARGS]            Run 'tox' test automation tool.
  refresh               Refresh requirements files.
  update                Update frontend dependencies.

OPTIONS:
  --help                Print usage
EOF
	exit 1
}

yesno() {
	while true; do
		echo "$1"
		read -r yesno
		case $yesno in
			Y|y|YES|Yes|yes)
				return 0
				;;
			N|n|NO|No|no)
				return 1
				;;
			*)
				echo "Please answer yes or no."
				;;
		esac
	done
}

frontend_deps() {
	if [ "$1" = "install" ] || [ "$1" = "update" ]; then
		"$NPM_CMD" "$1"
	fi
	./node_modules/.bin/gulp
}

wait_prepare() {
	echo "Collecting static assets, compressing and migrating..."
	while ! "$COMPOSE_CMD" ${COMPOSE_ARG:+"$COMPOSE_ARG"} exec "$SERVICE_WEB" ps -p 1 -o args= | grep -q "runserver"; do
		sleep 5
	done
}

docker_initialize() {
	if ! "$COMPOSE_CMD" ${COMPOSE_ARG:+"$COMPOSE_ARG"} exec "$SERVICE_WEB" "$MANAGE_CMD" dumpdata --no-color --format yaml users.user | grep -q "is_superuser: true"; then
		"$COMPOSE_CMD" ${COMPOSE_ARG:+"$COMPOSE_ARG"} exec "$SERVICE_WEB" djangoctl.sh initialize
	fi
}

virtualenv_initialize() {
	. .virtualenv/bin/activate
	if ! "$MANAGE_CMD" dumpdata --no-color --format yaml users.user | grep -q "is_superuser: true"; then
		./bin/djangoctl.sh initialize
	fi
	deactivate
}

virtualenv_install() {
	virtualenv -p python$PYTHON_VERSION .virtualenv
	.virtualenv/bin/pip install \
			    --no-cache-dir \
			    --no-deps \
			    --force-reinstall \
			    -e "."
	.virtualenv/bin/pip install \
			    --no-cache-dir \
			    --no-deps \
			    -r "./requirements-dev.txt"
}

has_command() {
	if ! which "$1" >/dev/null; then
		echo "ERROR: '$1' not found! Either not installed or PATH not set correctly." >&2
		exit 1
	fi
}

parse_args() {
	arg="$1"
	case $arg in
		compose)
			has_command "$COMPOSE_CMD"
			shift
			"$COMPOSE_CMD" ${COMPOSE_ARG:+"$COMPOSE_ARG"} "$@"
			return
			;;
		up)
			has_command "$COMPOSE_CMD"
			frontend_deps install
			shift
			"$COMPOSE_CMD" ${COMPOSE_ARG:+"$COMPOSE_ARG"} "$arg" -d "$@"
			wait_prepare
			docker_initialize
			echo "Services start-up completed."
			return
			;;
		shell)
			has_command "$COMPOSE_CMD"
			shift
			if [ -z "$1" ]; then
				echo "ERROR: No service name specified!" >&2
				usage
			fi
			if ! "$COMPOSE_CMD" ${COMPOSE_ARG:+"$COMPOSE_ARG"} exec "$1" "$SHELL_CMD"; then
				echo "Please make sure that the services are up!" >&2
				exit 1
			fi
			return
			;;
		clean)
			has_command "$COMPOSE_CMD"
			yesno "This action will delete all installation data! Are you sure? [Yes/No]"
			"$COMPOSE_CMD" ${COMPOSE_ARG:+"$COMPOSE_ARG"} down -v
			return
			;;
		django-admin)
			has_command "$COMPOSE_CMD"
			shift
			if ! "$COMPOSE_CMD" ${COMPOSE_ARG:+"$COMPOSE_ARG"} exec "$SERVICE_WEB" "$MANAGE_CMD" "$@"; then
				echo "Please make sure that the services are up!" >&2
				exit 1
			fi
			return
			;;
		tox)
			has_command "tox"
			shift
			"$TOX_CMD" "$@"
			return
			;;
		refresh)
			has_command "virtualenv"
			"$REFRESH_CMD"
			return
			;;
		update)
			has_command "npm"
			frontend_deps update
			return
			;;
		develop|develop_celery)
			has_command "virtualenv"
			if [ ! -d .virtualenv ]; then
				frontend_deps install
				virtualenv_install
				virtualenv_initialize
			fi
			. .virtualenv/bin/activate
			./bin/djangoctl.sh "$arg" .
			return
			;;
		remove)
			yesno "This action will delete all installation data! Are you sure? [Yes/No]"
			rm -rf ".virtualenv" "db.sqlite3" "media" "staticfiles"
			return
			;;
		*)
			usage
			;;
	esac
}

main() {
	if [ ! -f "$COMPOSE_FILE" ]; then
		echo "ERROR: No Docker Compose file found! Please run from top directory." >&2
		exit 1
	fi
	parse_args "$@"
}

main "$@"
