import os
from time import sleep
from datetime import datetime
import pytest

from wazuh_testing.tools.configuration import load_configuration_template, get_test_cases_data, \
                                              get_simulate_agent_configuration
from wazuh_testing.modules.eps import event_monitor as evm
from wazuh_testing.modules.eps import PERCENTAGE_PROCESS_MSGS, QUEUE_SIZE


pytestmark = [pytest.mark.server]

# Reference paths
TEST_DATA_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')
CONFIGURATIONS_PATH = os.path.join(TEST_DATA_PATH, 'configuration_template')
TEST_CASES_PATH = os.path.join(TEST_DATA_PATH, 'test_cases')

# Configuration and cases data
configurations_path = os.path.join(CONFIGURATIONS_PATH, 'configuration_start_dropping_events_when_queue_full.yaml')
configurations_simulate_agent_path = os.path.join(TEST_DATA_PATH,
                                                  'configuration_simulate_agent.yaml')
t1_cases_path = os.path.join(TEST_CASES_PATH, 'cases_start_dropping_events.yaml')


# Start dropping events test configurations (t1)
t1_configuration_parameters, t1_configuration_metadata, t1_case_ids = get_test_cases_data(t1_cases_path)
t1_configurations = load_configuration_template(configurations_path, t1_configuration_parameters,
                                                t1_configuration_metadata)

# Get simulate agent configurations (t1)
params_start_dropping_events_when_queue_full = get_simulate_agent_configuration(configurations_simulate_agent_path)
timeframe_eps_t1 = [metadata['timeframe'] for metadata in t1_configuration_metadata]
total_msg = 16500  # of 1Kb message of 16384 Kb of queue size. Total dropped aproximatelly 116
expected_msg_dropped = total_msg - QUEUE_SIZE
params_start_dropping_events_when_queue_full.update({'total_msg': total_msg})


@pytest.mark.parametrize('configuration, metadata', zip(t1_configurations, t1_configuration_metadata), ids=t1_case_ids)
@pytest.mark.parametrize('configure_local_internal_options_eps', [timeframe_eps_t1], indirect=True)
@pytest.mark.parametrize('simulate_agent', [params_start_dropping_events_when_queue_full], indirect=True)
def test_start_dropping_events_when_queue_full(configuration, metadata, set_wazuh_configuration_eps,
                                               truncate_monitored_files, restart_wazuh_daemon_function,
                                               simulate_agent):
    '''
    description: Check that the `events_dropped` value in the `/var/ossec/var/run/wazuh-analysisd.state` file must
                 be greater than 1 and, `event_queue_usage` is equal to 1
                 than 1.0.

    test_phases:
        - Set a custom Wazuh configuration.
        - Truncate logs files.
        - Restart wazuh-daemons.
        - Execute agent simulated script.

    wazuh_min_version: 4.4.0

    tier: 0

    parameters:
        - configuration:
            type: dict
            brief: Wazuh configuration data. Needed for set_wazuh_configuration fixture.
        - metadata:
            type: dict
            brief: Wazuh configuration metadata.
        - set_wazuh_configuration_eps:
            type: fixture
            brief: Set the wazuh configuration according to the configuration data.
        - truncate_monitored_files:
            type: fixture
            brief: Truncate all the log files and json alerts files before and after the test execution.
        - restart_wazuh_daemon_function:
            type: fixture
            brief: Restart all the wazuh daemons.
        - simulate_agent:
            type: fixture
            brief: Execute a script that simulate agent and send `logcolector` logs to the manager.

    assertions:
        - The `events_processed` value in the `/var/ossec/var/run/wazuh-analysisd.state` file must be lower or equal
          than `maximum` * `timeframe` and greater than a percentage of `maximum` * `timeframe` to confirm that
          `events_processed` is not null. The `events_received` value must be greater than `events_processed` and,
          the `events_dropped` value greater than 0 and finaly, `event_queue_usage` is equal to 1.0.

    input_description:
        - The `cases_start_queueing_events.yaml` file provides the module configuration for this test.
    '''
    # Wait 'timeframe' / 2 second to read the wazuh-analysisd.state to ensure that has corrects values
    sleep(metadata['timeframe'] / 2)
    events_processed = evm.get_analysisd_state('events_processed')
    events_received = evm.get_analysisd_state('events_received')
    events_dropped = evm.get_analysisd_state('events_dropped')
    event_queue_usage = evm.get_analysisd_state('event_queue_usage')

    # Check that processed events reach the EPS limit
    assert events_processed <= float(metadata['maximum'] * metadata['timeframe']) and \
        events_processed >= float(metadata['maximum'] * metadata['timeframe']) * PERCENTAGE_PROCESS_MSGS, \
        'events_processed must be lower or equal to maximum * timeframe'

    # Check that events continue receiving although the EPS limit was reached
    assert events_received > events_processed, 'events_received must be bigger than events_processed'

    # Check that there is no event dropped and the queue usage is less than 1.0 (100%). This means the queue is not full
    assert events_dropped >= int(expected_msg_dropped * PERCENTAGE_PROCESS_MSGS) \
        and events_dropped <= int(expected_msg_dropped * (1 + (1 - PERCENTAGE_PROCESS_MSGS))), 'events_dropped must '\
        'be in the range of (total_msg - QUEUE_SIZE)'

    # Check that there is no event dropped and the queue usage is less than 1.0 (100%). This means the queue is not full
    assert event_queue_usage == 1.0, 'event_queue_usage must be 1.0'

    # Check that events_dropped are in the range of events_received - events_processed
    assert events_processed <= events_received - events_dropped, 'events_processed must be lower than' \
        'events_received - events_dropped'
