#!/usr/bin/env bash
#
# To run a script
# ./run.sh [image:tag] [./script]

set -euo pipefail

docker run \
  -it \
  --rm \
  --env AWS_SECRET_ACCESS_KEY \
  --env AWS_ACCESS_KEY_ID \
  --env AWS_DEFAULT_REGION \
  "$@"
