#!/usr/bin/env python
#
# This script:
# 1. Finds CloudFormation stack by --tags
# 2. Gets ALB ARN and ALB Listener ARN from the CF stack output by --alb_key and --listener_key
# 3. Gets ALB Listeners by ARN and builds URLs for graceful stop
# 4. POSTs the request to the URLs to stop the service
#
# Important: Stack's tags must match FULLY with --tags
# Important: --tags, --alb_key and --listener_key parameters are compulsory
#
# Example for DEDUP service:
# AWS_DEFAULT_REGION=us-east-1 ./stop_all.py --tags="component=base,Type=dedup" --alb_key=ALBArn --listener_key=ALBListenerArn -v

from __future__ import print_function
import argparse
import boto3
import os
import requests
import sys
import json

def get_stop_urls(alb_arn, alb_listener_arn, region):
    alb_client = boto3.client('elbv2', region_name=region)

    response = alb_client.describe_load_balancers(LoadBalancerArns=[alb_arn], )
    alb_dns_name = response['LoadBalancers'][0]['DNSName']

    response = alb_client.describe_rules(ListenerArn=alb_listener_arn, )

    urls = []

    for rule in response['Rules']:
        if len(rule['Conditions']) == 0:
            urls.append('https://' + alb_dns_name + '/stop')
        else:
            for condition in rule['Conditions']:
                for value in condition['Values']:
                    urls.append('https://' + alb_dns_name + value.replace('*', 'stop'))

    return urls


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tags', required=True)
    parser.add_argument('--alb_key', required=True)
    parser.add_argument('--listener_key', required=True)
    parser.add_argument('-v', '--verbose', default=False, action='store_true')
    return parser.parse_args()


def parse_tags(tags_string):
    parts = tags_string.split(',')
    kvs = (part.split('=') for part in parts if part)
    return {key: value for (key, value) in kvs}


def match_tags(stack, tags):
    if len(stack.tags) != len(tags):
        return False

    return all(tags.get(tag['Key'], None) == tag['Value'] for tag in stack.tags)


def get_stack_by_tags(tags, verbose, region):
    cloudformation = boto3.resource('cloudformation', region_name=region)
    stacks = cloudformation.stacks.all()

    matched_stacks = [stack for stack in stacks if match_tags(stack, tags)]
    if len(matched_stacks) != 1:
        if verbose:
            print('Found {} stacks with {}'.format(len(matched_stacks), tags), file=sys.stderr)
        return None
    return matched_stacks[0]


def get_stack_output(stack, key, verbose):
    matched_outputs = [output for output in stack.outputs if output['OutputKey'] == key]
    if len(matched_outputs) != 1:
        if verbose:
            print('Found {} outputs with {} in stack {}'.format(len(matched_outputs), key, stack.stack_name), file=sys.stderr)
        return None
    return matched_outputs[0]['OutputValue']


def stop(url, attempts):
    for i in range(1, attempts + 1):
        try:
            print('Stopping: {}'.format(url))
            r = requests.post(url, verify=False)
        except Exception as e:
            print('Caught exception {}'.format(e))
            sys.exit(1)
        else:
            print('Received {}:{} from {}'.format(r.status_code, r.text.rstrip(), url))
            if r.status_code == 200:
                print('Successfully stopped {}'.format(url))
                return True
            elif r.status_code in [503, 404]:
                print('Stop attempt {} returns {} status code. Ignoring...'.format(url, r.status_code))
                return True

    print('Failed to stop {} after {} attempts'.format(ip, attempts))
    return False


def main():
    region = os.environ.get('AWS_DEFAULT_REGION')
    print('AWS_DEFAULT_REGION = {}'.format(region))

    args = get_args()
    tags = parse_tags(args.tags)

    print('tags = {}'.format(json.dumps(tags)))

    stack = get_stack_by_tags(tags, args.verbose, region)
    if stack is None:
        return

    alb_arn = get_stack_output(stack, args.alb_key, args.verbose)
    alb_listener_arn = get_stack_output(stack, args.listener_key, args.verbose)

    print('alb_arn = {}'.format(alb_arn))
    print('alb_listener_arn = {}'.format(alb_listener_arn))

    if (alb_arn is None) or (alb_listener_arn is None):
        sys.exit(1)

    urls = get_stop_urls(alb_arn, alb_listener_arn, region)

    if len(urls) == 0:
        print('No rules defined in the ALB - nothing to stop')
    else:
        for url in urls:
            if not stop(url, attempts=10):
                print('Failed to stop {}'.format(url))
                sys.exit(1)

    print('\nDone!\n')


if __name__ == '__main__':
    main()
