#!/bin/bash

set -euo pipefail

export BUILD_NUMBER=$BUILDKITE_BUILD_NUMBER
export TRIGGER_MESSAGE="Deploying ${TRIGGER_APPLICATION} Build ${BUILD_NUMBER} Commit: ${BUILDKITE_COMMIT}"

echo "--- :package: Enabling Deployments onto other accounts"

NEW_BUILD_JSON=$(
  curl \
    "https://api.buildkite.com/v2/organizations/${BUILDKITE_ORGANIZATION_SLUG}/pipelines/unlockd${ACCOUNT_ALIAS}-${TRIGGER_APPLICATION}-deployment/builds" \
    -X POST \
    --fail \
    -s \
    -H "Authorization: Bearer ${TRIGGER_API_ACCESS_TOKEN}" \
    -d "{
      \"commit\": \"${BUILDKITE_COMMIT}\",
      \"branch\": \"${BUILDKITE_BRANCH}\",
      \"message\": \"${TRIGGER_MESSAGE}\",
      \"env\": {
        \"BUILD_NUMBER\": \"${BUILD_NUMBER}\",
        \"PLATFORM_AMI_BUILD\": \"${PLATFORM_AMI_BUILD}\",
        \"ENVIRONMENT\": \"${TRIGGER_ENVIRONMENT}\",
        \"BUILD_CREATOR\": \"${BUILDKITE_BUILD_CREATOR}\",
        \"REPOSITORY_URL\": \"${REPOSITORY_URL}\"
      }
    }"
)

BUILD_URL=$(echo "$NEW_BUILD_JSON" | python -c 'import sys, json; print json.load(sys.stdin)["url"]')

echo "Build URL: $BUILD_URL"

BUILD_JSON=$( curl "$BUILD_URL" -s --fail -H "Authorization: Bearer ${TRIGGER_API_ACCESS_TOKEN}" )
