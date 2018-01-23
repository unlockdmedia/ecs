#!/bin/bash

set -euo pipefail

echo "Looking up latest Platform AMI"

PLATFORM_AMI_NAME=$(aws ec2 describe-images --filters Name=tag:Name,Values="Unlockd Platform Base Image" Name=tag:Provisioner,Values="Packer" | jq -r .Images[].Name | sort -r  | head -1)
PLATFORM_AMI_BUILD=$(aws ec2 describe-images --filters Name=name,Values="${PLATFORM_AMI_NAME}" | jq -r '.Images[].Tags[] | select(.Key=="Build") | .Value')

if [[ "x${PLATFORM_AMI_BUILD}" == "x" ]]; then
  echo "Platform AMI ID not found"
  exit 1
fi

echo "Using Platform AMI Build: ${PLATFORM_AMI_BUILD}"

buildkite-agent meta-data set "PLATFORM_AMI_BUILD" "${PLATFORM_AMI_BUILD}"
