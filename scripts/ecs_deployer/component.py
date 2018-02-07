from __future__ import print_function
import collections
from helper import *

class Component(object):
    def __init__(self, config, name, environment, region, stack_outputs):
        self.config = config
        self.name = name
        self.environment = environment
        self.region = region
        self.stack_outputs = stack_outputs

        self.inputs = self.get_component_inputs()
        self.settings = self.get_component_settings(name)
        self.capabilities = self.get_component_capabilities()
        self.config_dir = self.get_component_config_dir()
        self.tags = self.get_component_tags()
        self.notify = self.get_component_notify()
        self.strategy = self.get_component_deployment_strategy()
        self.defined_outputs = self.get_component_defined_outputs()

    def get_component_settings(self, component_name):
        settings = self.config[':components'][':' + component_name][':settings']
        if settings[':region'] != self.region or settings[':environment'] != self.environment:
            raise Exception("setting section of the config-file does not match environment or region")
        return settings

    def get_component_inputs(self):
        def parse_input(key, value):
            if isinstance(value, dict) and ':component' in value and ':output-key' in value:
                component = value[':component']
                settings = self.get_component_settings(component)
                stack_name = self.get_stack_name(settings)
                output_key = value[':output-key']
                return { 'ParameterKey': key[1:], 'ParameterValue': self.stack_outputs[stack_name][output_key] }
            else:
                if isinstance(value, bool):
                    pval = str(value).lower()
                elif value is None:
                    pval = ''
                else:
                    pval = str(value)
                return { 'ParameterKey': key[1:], 'ParameterValue': pval }

        inputs = self.config[':components'][':' + self.name][':inputs']
        if inputs[':region'] != self.region or inputs[':environment'] != self.environment:
            raise Exception("inputs section of the config-file does not match environment or region")
        ignored_inputs = set([':application', ':component', ':environment', ':region'])
        parsed_inputs = [parse_input(k, v) for k, v in inputs.iteritems() if k not in ignored_inputs]
        return parsed_inputs

    def get_component_capabilities(self):
        return self.config[':components'][':' + self.name].get(':capabilities', [])

    def get_component_config_dir(self):
        return self.config[':components'][':' + self.name][':config_dir']

    def get_component_tags(self):
        tags = self.config[':components'][':' + self.name].get(':tags', {})
        return [{'Key': k[1:], 'Value': v} for k, v in tags.iteritems()]

    def get_component_notify(self):
        return self.config[':components'][':' + self.name].get(':notify', [])

    def get_component_deployment_strategy(self):
        environmental_strategy = self.config \
            .get(':environments', {}) \
            .get(':' + self.environment, {}) \
            .get(':components', {}) \
            .get(':' + self.name, {}) \
            .get(':deployment-strategy')

        if environmental_strategy:
            return environmental_strategy

        return self.config[':components'][':' + self.name].get(':deployment-strategy', 'ecs-replace-when-necessary')

    def get_component_defined_outputs(self):
        return self.config[':components'][':' + self.name].get(':defined_outputs', {})

    def get_stack_name(self, settings):
        return '{}-{}-{}'.format(settings[':application'], settings[':environment'], settings[':component'])
