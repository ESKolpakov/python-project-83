#!/usr/bin/env bash
# build.sh

curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
make install
psql -d $DATABASE_URL -f database.sql