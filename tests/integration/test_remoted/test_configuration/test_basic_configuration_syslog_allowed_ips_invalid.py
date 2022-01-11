# Copyright (C) 2015-2021, Wazuh Inc.
# Created by Wazuh, Inc. <info@wazuh.com>.
# This program is free software; you can redistribute it and/or modify it under the terms of GPLv2

import os
import pytest

import wazuh_testing.remote as remote
from wazuh_testing.tools.configuration import load_wazuh_configurations
from wazuh_testing.tools.monitoring import REMOTED_DETECTOR_PREFIX
import wazuh_testing.generic_callbacks as gc
from wazuh_testing.tools import WAZUH_CONF_RELATIVE

# Marks
pytestmark = pytest.mark.tier(level=0)

# Configuration
test_data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')
configurations_path = os.path.join(test_data_path, 'wazuh_basic_configuration.yaml')

parameters = [
    {'ALLOWED': '127.0.0.0.0'},
    {'ALLOWED': 'Testing'},
    {'ALLOWED': '127.0.0.0/7890'},
    {'ALLOWED': '127.0.0.0/7890'},
    {'ALLOWED': '::1::1'},
    {'ALLOWED': 'Testing'},
    {'ALLOWED': '::1/512'},
    {'ALLOWED': '::1/512'}
]

metadata = [
    {'allowed-ips': '127.0.0.0.0'},
    {'allowed-ips': 'Testing'},
    {'allowed-ips': '127.0.0.0/7890'},
    {'allowed-ips': '127.0.0.0/7890'},
    {'allowed-ips': '::1::1'},
    {'allowed-ips': 'Testing'},
    {'allowed-ips': '::1/512'},
    {'allowed-ips': '::1/512'}
]

configurations = load_wazuh_configurations(configurations_path, "test_allowed_ips_invalid",
                                           params=parameters, metadata=metadata)
configuration_ids = [f"{x['ALLOWED']}" for x in parameters]


# fixtures
@pytest.fixture(scope="module", params=configurations, ids=configuration_ids)
def get_configuration(request):
    """Get configurations from the module."""
    return request.param


def test_allowed_ips_invalid(get_configuration, configure_environment, restart_remoted):
    """Test if `wazuh-remoted` fails when invalid `allowed-ips` label value is set.

    Raises:
        AssertionError: if `wazuh-remoted` does not show in `ossec.log` expected error message.
    """
    cfg = get_configuration['metadata']

    log_callback = remote.callback_error_invalid_ip(cfg['allowed-ips'])
    wazuh_log_monitor.start(timeout=5, callback=log_callback,
                            error_message="The expected error output has not been produced")

    log_callback = gc.callback_error_in_configuration('ERROR', prefix=REMOTED_DETECTOR_PREFIX,
                                                      conf_path=WAZUH_CONF_RELATIVE)
    wazuh_log_monitor.start(timeout=5, callback=log_callback,
                            error_message="The expected error output has not been produced")

    log_callback = gc.callback_error_in_configuration('CRITICAL', prefix=REMOTED_DETECTOR_PREFIX,
                                                      conf_path=WAZUH_CONF_RELATIVE)
    wazuh_log_monitor.start(timeout=5, callback=log_callback,
                            error_message="The expected error output has not been produced")
