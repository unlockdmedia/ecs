#!/usr/bin/env python
#
# Poll until the ECS service and its tasks are stable

from __future__ import print_function
import argparse
import datetime
import itertools
import time
import sys
import boto3

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cluster-name', dest='cluster_name', required=True, help='Name of the ECS Cluster')
    parser.add_argument('--service-arn', dest='service_arn', required=True, help='ARN of the ECS Service')
    parser.add_argument('--full-image-name', dest='full_image_name', required=False, help='Full image name: e.g. REPO_URL:BUILD_NUMBER')
    parser.add_argument('--attempts', default=30, type=int, help='Number of poll attempts before reporting error')
    parser.add_argument('--interval', default=5, type=int, help='Number of seconds between each attempt')
    return parser.parse_args()

def log(message):
    print('{} {}'.format(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), message))

def one(iterables):
    heads = list(itertools.islice(iterables, 2))
    if len(heads) == 0:
        raise Exception('Try to get one element from an empty iterable')
    if len(heads) > 1:
        raise Exception('More than 1 elements in {}'.format(iterables))
    return heads[0]

def flatten(listoflists):
    return [item for l in listoflists for item in l]

def paginate(l, page_size):
    return [l[i:i+page_size] for i in xrange(0, len(l), page_size)]

def get_service(cluster_name, service_arn, ecs_client):
    response = ecs_client.describe_services(cluster=cluster_name, services=[service_arn])
    if len(response['failures']) > 0:
        raise Exception("Failed to describe ECS services. {}".format(response['failures']))
    return one(response['services'])

def get_tasks(cluster_name, service_arn, ecs_client):
    def get_tasks_batch(arns):
        response = ecs_client.describe_tasks(cluster=cluster_name, tasks=arns)
        if len(response['failures']) > 0:
            raise Exception("Failed to describe ECS tasks. {}".format(response['failures']))
        return response['tasks']

    task_arns = flatten(p['taskArns'] for p in ecs_client.get_paginator('list_tasks').paginate(cluster=cluster_name, serviceName=service_arn, desiredStatus='RUNNING'))
    tasks = flatten(get_tasks_batch(arns) for arns in paginate(task_arns, page_size=100))
    return tasks

def poll(cluster_name, service_arn, attempts, interval, ecs_client):
    def is_service_stable(service, tasks):
        if service['runningCount'] < service['desiredCount']:
            log('Only {} tasks are running. Require at least {} tasks.'.format(service['runningCount'], service['desiredCount']))
            return False

        if len(tasks) != service['runningCount']:
            log('Actual tasks count ({}) has not matched runningCount ({}).'.format(len(tasks), service['runningCount']))
            return False

        if len(service['deployments']) != 1:
            log('There are {} deployments.'.format(len(service['deployments'])))
            return False

        if not last_service_snapshot:
            log('This is the first check. More data is required.')
            return False

        if len(last_service_snapshot['events']) == 0 or len(service['events']) == 0:
            log('No service events collected. More data is required.')
            return False

        if last_service_snapshot['events'][0]['id'] != service['events'][0]['id']:
            log('Latest service event has changed since last poll. The service is not stable yet.')
            return False

        log('Last event is: {}'.format(service['events'][0]['message']))

        if 'has reached a steady state' not in service['events'][0]['message'].lower():
            log('Latest service event does not indicate the service has been stable yet.')
            return False

        if {task['taskArn'] for task in tasks} != {task['taskArn'] for task in last_tasks_snapshot}:
            log('Tasks have changed since last poll. The service is not sable yet.')
            return False

        if any(task['taskDefinitionArn'] != service['taskDefinition'] for task in tasks):
            log("Not all tasks' task definition match the service's task definition.")
            return False

        return True


    last_service_snapshot = None
    last_tasks_snapshot = []

    for i in xrange(attempts):
        if i > 0:
            log('Attempting {} of {}...'.format(i+1, attempts))

        service = get_service(cluster_name, service_arn, ecs_client)
        tasks = get_tasks(cluster_name, service_arn, ecs_client)

        if is_service_stable(service, tasks):
            return service, True

        if i < attempts - 1:
            time.sleep(interval)

        last_service_snapshot = service
        last_tasks_snapshot = tasks

        sys.stdout.flush()

    return last_service_snapshot, False

def match_image(service, full_image_name, ecs_client):
    containers = ecs_client.describe_task_definition(taskDefinition=service['taskDefinition'])['taskDefinition']['containerDefinitions']
    return any(container['image'] == full_image_name for container in containers)

def main():
    args = get_args()
    ecs_client = boto3.client('ecs')

    service, stable = poll(cluster_name=args.cluster_name, service_arn=args.service_arn, attempts=args.attempts, interval=args.interval, ecs_client=ecs_client)

    if stable:
        log('Service {} is stable.'.format(args.service_arn))

        if args.full_image_name:
            if match_image(service=service, full_image_name=args.full_image_name, ecs_client=ecs_client):
                log('Containers use {}'.format(args.full_image_name))
            else:
                log('Containers do not match {}'.format(args.full_image_name))
                sys.exit(1)
    else:
        log('Service {} is still not stable after {} polls.'.format(args.service_arn, args.attempts))
        sys.exit(1)

if __name__ == '__main__':
    main()
