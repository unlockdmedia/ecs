from __future__ import print_function
import json
import boto3
from helper import *

class AWS(object):
    def __init__(self, region):
        self.cf_resource = boto3.resource('cloudformation', region_name=region)
        self.cf_client = boto3.client('cloudformation', region_name=region)
        self.asg_client = boto3.client('autoscaling', region_name=region)
        self.elb_client = boto3.client('elb', region_name=region)
        self.ecs_client = boto3.client('ecs', region_name=region)

    def get_all_cf_stack_outputs(self):
        stacks = self.cf_resource.stacks.all()
        return { stack.stack_name: { output['OutputKey']: output['OutputValue'] for output in (stack.outputs or []) } for stack in stacks }

    def get_cf_stack(self, stack_name):
        return one(self.cf_client.describe_stacks(StackName=stack_name)['Stacks'])

    def is_cf_stack_changed(self, existing_stack_name, new_template, new_inputs, new_tags):
        existing_template = json.dumps(self.cf_client.get_template(StackName=existing_stack_name)['TemplateBody'], sort_keys=True)
        template_sorted = json.dumps(json.loads(new_template), sort_keys=True)

        input_keys_to_compare = set(parameter['ParameterKey'] for parameter in self.cf_client.get_template_summary(StackName=existing_stack_name)['Parameters'] if not parameter['NoEcho'])
        existing_stack = one(self.cf_client.describe_stacks(StackName=existing_stack_name)['Stacks'])
        existing_inputs = sorted((p for p in existing_stack['Parameters'] if p['ParameterKey'] in input_keys_to_compare), key=lambda i: i['ParameterKey'])
        inputs_sorted = sorted((i for i in new_inputs if i['ParameterKey'] in input_keys_to_compare), key=lambda i: i['ParameterKey'])

        delta_keys1 = [p['ParameterKey'] for p in existing_inputs if p not in inputs_sorted]
        delta_keys2 = [p['ParameterKey'] for p in inputs_sorted if p not in existing_inputs]
        delta_keys = sorted(list(set(delta_keys1 + delta_keys2)))

        existing_tags = sorted(existing_stack['Tags'], key=lambda tag: tag['Key'])
        tags_sorted = sorted(new_tags, key=lambda tag: tag['Key'])

        return {'template': existing_template != template_sorted,
                'inputs': delta_keys,
                'tags': existing_tags != tags_sorted }

    def create_stack(self, args):
        waiter = self.cf_client.get_waiter('stack_create_complete')
        stack_id = self.cf_client.create_stack(**args)['StackId']
        waiter.wait(StackName=stack_id)

    def update_stack(self, args):
        waiter = self.cf_client.get_waiter('stack_update_complete')
        stack_id = self.cf_client.update_stack(**args)['StackId']
        waiter.wait(StackName=stack_id)

    def delete_stack(self, stack_name):
        waiter = self.cf_client.get_waiter('stack_delete_complete')
        self.cf_client.delete_stack(StackName=stack_name)
        waiter.wait(StackName=stack_name)

    def get_output_from_stack(self, stack_name, output_key):
        stack = one(self.cf_client.describe_stacks(StackName=stack_name)['Stacks'])
        outputs = stack['Outputs']
        value = next((output['OutputValue'] for output in outputs if output['OutputKey'] == output_key), None)
        if value is None:
            raise Exception('Cannot find output {} from stack {}'.format(output_key, stack_name))
        return value

    def get_asgs(self, asg_names):
        asgs = self.asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=asg_names)['AutoScalingGroups']
        return [one(asg for asg in asgs if asg['AutoScalingGroupName'] == asg_name) for asg_name in asg_names]

    def set_desired_capacity(self, asg_name, desired_capacity):
        self.asg_client.set_desired_capacity(AutoScalingGroupName=asg_name, DesiredCapacity=desired_capacity)

    def get_healthy_instance_count(self, asg_name):
        asg = one(self.asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])['AutoScalingGroups'])
        instances = asg['Instances']
        healthy_instance_ids = {i['InstanceId'] for i in instances if i['HealthStatus'].upper() == 'HEALTHY'}
        if len(asg['LoadBalancerNames']) > 0:
            elb_instances = flatten(self.elb_client.describe_instance_health(LoadBalancerName=elb_name) for elb_name in asg['LoadBalancerNames'])
            inservice_instance_ids = {i['InstanceId'] for i in elb_instances if i['State'].upper() == 'INSERVICE'}
            healthy_instance_ids &= inservice_instance_ids
        return len(healthy_instance_ids)

    def get_ecs_instances(self, cluster_name):
        instance_arns = flatten(p['containerInstanceArns'] for p in self.ecs_client.get_paginator('list_container_instances').paginate(cluster=cluster_name, status='ACTIVE'))
        response = self.ecs_client.describe_container_instances(cluster=cluster_name, containerInstances=instance_arns)
        if len(response['failures']) > 0:
            raise Exception("Failed to describe ECS container instances. {}".format(response['failures']))

        return response['containerInstances']

    def get_ecs_tasks(self, cluster_name):
        def get_tasks(arns):
            response = self.ecs_client.describe_tasks(cluster=cluster_name, tasks=arns)
            if len(response['failures']) > 0:
                raise Exception("Failed to describe ECS tasks. {}".format(response['failures']))
            return response['tasks']

        task_arns = flatten(p['taskArns'] for p in self.ecs_client.get_paginator('list_tasks').paginate(cluster=cluster_name, desiredStatus='RUNNING'))
        tasks = flatten(get_tasks(arns) for arns in paginate(task_arns, page_size=100))
        return tasks

    def get_ecs_services(self, cluster_name):
        def get_services(arns):
            response = self.ecs_client.describe_services(cluster=cluster_name, services=arns)
            if len(response['failures']) > 0:
                raise Exception("Failed to describe ECS services. {}".format(response['failures']))
            return response['services']

        service_arns = flatten(p['serviceArns'] for p in self.ecs_client.get_paginator('list_services').paginate(cluster=cluster_name))
        services = flatten(get_services(arns) for arns in paginate(service_arns, page_size=10))
        return services

    def drain_ecs_instances(self, cluster_name, existing_asg_name, new_asg_name):
        def drain(ecs_instances):
            instance_arns_to_drain = [i['containerInstanceArn'] for i in ecs_instances if i['status'].upper() == 'ACTIVE']
            if len(instance_arns_to_drain) > 0:
                response = self.ecs_client.update_container_instances_state(cluster=cluster_name, containerInstances=instance_arns_to_drain, status='DRAINING')
                if len(response['failures']) > 0:
                    raise Exception("Failed to drain ECS instance. {}".format(response['failures']))

        all_ecs_instances = self.get_ecs_instances(cluster_name)

        existing_asg, new_asg = self.get_asgs([existing_asg_name, new_asg_name])

        existing_instance_ids = { i['InstanceId'] for i in existing_asg['Instances'] }
        existing_ecs_instances = [i for i in all_ecs_instances if i['ec2InstanceId'] in existing_instance_ids]
        existing_instance_arns = { i['containerInstanceArn'] for i in existing_ecs_instances }

        drain(existing_ecs_instances)

        new_instance_ids = { i['InstanceId'] for i in new_asg['Instances'] }
        new_ecs_instances = [i for i in all_ecs_instances if i['ec2InstanceId'] in new_instance_ids]
        new_instance_arns = { i['containerInstanceArn'] for i in new_ecs_instances }

        all_tasks = self.get_ecs_tasks(cluster_name=cluster_name)
        existing_tasks = [t for t in all_tasks if t['containerInstanceArn'] in existing_instance_arns]
        new_tasks = [t for t in all_tasks if t['containerInstanceArn'] in new_instance_arns]

        return existing_tasks, new_tasks
