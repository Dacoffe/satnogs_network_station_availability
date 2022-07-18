#!/bin/sh -e
#
# Script to refresh requirements.txt file
#
# Copyright (C) 2019-2022 Libre Space Foundation <https://libre.space/>
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

EXCLUDE_REGEXP="^\\(pkg[-_]resources\\|satnogs-network\\)"
COMPATIBLE_REGEXP=""
VIRTUALENV_DIR=$(mktemp -d)
PIP_COMMAND="$VIRTUALENV_DIR/bin/pip"
PYTHON_VERSION="3.9"
REQUIREMENTS="
comm
grep
sed
sort
virtualenv
"

# Check for required utilities
for req in $REQUIREMENTS; do
	if ! which "$req" >/dev/null; then
		if [ -z "$has_missing" ]; then
			echo "$(basename "$0"): Missing script requirements!" 1>&2
			echo "Please install:" 1>&2
			has_missing=1
		fi
		echo " - '$req'" 1>&2
	fi
done
if [ -n "$has_missing" ]; then
	exit 1
fi

# Create virtualenv
virtualenv -p python$PYTHON_VERSION "$VIRTUALENV_DIR"

# Install package with dependencies
"$PIP_COMMAND" install --no-cache-dir --force-reinstall .

# Create file header warnings
for filename in constraints.txt requirements.txt requirements-dev.txt; do
	cat << EOF > "$filename"
# This is a generated file; DO NOT EDIT!
#
# Please edit 'setup.cfg' to modify top-level dependencies and run
# './contrib/refresh-requirements.sh to regenerate this file

EOF
done

# Create requirements file from installed dependencies
"$PIP_COMMAND" freeze | grep -v "$EXCLUDE_REGEXP" >> requirements.txt

# Install development package with dependencies
"$PIP_COMMAND" install --no-cache-dir .[dev]

# Create development requirements file from installed dependencies
echo "-r requirements.txt" >> requirements-dev.txt
_tmp_requirements_dev=$(mktemp)
"$PIP_COMMAND" freeze | grep -v "$EXCLUDE_REGEXP" | sort > "$_tmp_requirements_dev"
sort < requirements.txt | comm -13 - "$_tmp_requirements_dev" >> requirements-dev.txt

# Create constraints file from installed dependencies
cat "$_tmp_requirements_dev" >> constraints.txt
rm -f "$_tmp_requirements_dev"

# Set compatible release packages
if [ -n "$COMPATIBLE_REGEXP" ]; then
	sed -i 's/'"$COMPATIBLE_REGEXP"'==\([0-9]\+\)\(\.[0-9]\+\)\+$/\1~=\2.0/' requirements.txt
	sed -i 's/'"$COMPATIBLE_REGEXP"'==\([0-9]\+\)\(\.[0-9]\+\)\+$/\1~=\2.0/' requirements-dev.txt
	sed -i 's/'"$COMPATIBLE_REGEXP"'==\([0-9]\+\)\(\.[0-9]\+\)\+$/\1~=\2.0/' constraints.txt
fi

# Verify dependency compatibility
"$PIP_COMMAND" check

# Cleanup
rm -rf "$VIRTUALENV_DIR"
