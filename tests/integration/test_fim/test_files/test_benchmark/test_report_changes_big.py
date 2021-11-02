'''
copyright: Copyright (C) 2015-2021, Wazuh Inc.

           Created by Wazuh, Inc. <info@wazuh.com>.

           This program is free software; you can redistribute it and/or modify it under the terms of GPLv2

type: integration

brief: File Integrity Monitoring (FIM) system watches selected files and triggering alerts when these files
       are modified. Specifically, these tests will check if the 'wazuh-syscheckd' daemon generates the 'diff'
       files on large amounts of files and files with a large size using the 'report_changes' feature.
       The FIM capability is managed by the 'wazuh-syscheckd' daemon, which checks configured files
       for changes to the checksums, permissions, and ownership.

tier: 3

modules:
    - fim

components:
    - agent
    - manager

daemons:
    - wazuh-syscheckd

os_platform:
    - linux
    - windows

os_version:
    - Arch Linux
    - Amazon Linux 2
    - Amazon Linux 1
    - CentOS 8
    - CentOS 7
    - CentOS 6
    - Ubuntu Focal
    - Ubuntu Bionic
    - Ubuntu Xenial
    - Ubuntu Trusty
    - Debian Buster
    - Debian Stretch
    - Debian Jessie
    - Debian Wheezy
    - Red Hat 8
    - Red Hat 7
    - Red Hat 6
    - Windows 10
    - Windows 8
    - Windows 7
    - Windows Server 2019
    - Windows Server 2016
    - Windows Server 2012
    - Windows Server 2003
    - Windows XP

references:
    - https://documentation.wazuh.com/current/user-manual/capabilities/file-integrity/index.html
    - https://documentation.wazuh.com/current/user-manual/reference/ossec-conf/syscheck.html

pytest_args:
    - fim_mode:
        realtime: Enable real-time monitoring on Linux (using the 'inotify' system calls) and Windows systems.
        whodata: Implies real-time monitoring but adding the 'who-data' information.
    - tier:
        0: Only level 0 tests are performed, they check basic functionalities and are quick to perform.
        1: Only level 1 tests are performed, they check functionalities of medium complexity.
        2: Only level 2 tests are performed, they check advanced functionalities and are slow to perform.

tags:
    - fim_benchmark
'''
import os
import sys
from datetime import datetime
from statistics import mean, median

import pandas
import psutil
import pytest
from wazuh_testing.fim import LOG_FILE_PATH, WAZUH_PATH, REGULAR, generate_params, create_file, \
    callback_detect_event, check_time_travel
from wazuh_testing.tools import PREFIX
from wazuh_testing.tools.configuration import load_wazuh_configurations, check_apply_test
from wazuh_testing.tools.monitoring import FileMonitor

# Marks

pytestmark = pytest.mark.tier(level=3)

# Variables

current_datetime = datetime.now().strftime("%d%m%Y_%H%M%S")
metrics_name = 'report_changes_benchmark_{0}.csv'.format(current_datetime)
metrics_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'metrics')
metrics_path = os.path.join(metrics_dir, metrics_name)
test_directories = [os.path.join(PREFIX, 'testdir1')]
directory_str = ','.join(test_directories)
test_data_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')
configurations_path = os.path.join(test_data_path, 'wazuh_conf.yaml')
testdir1 = test_directories[0]

wazuh_log_monitor = FileMonitor(LOG_FILE_PATH)
timeout = 240 if sys.platform == 'win32' else 160

process = psutil.Process(os.getpid())

# Configurations

conf_params, conf_metadata = generate_params(extra_params={'TEST_DIRECTORIES': directory_str,
                                                           'REPORT_CHANGES': {'report_changes': 'yes'},
                                                           'MODULE_NAME': __name__})
configurations = load_wazuh_configurations(configurations_path, __name__, params=conf_params, metadata=conf_metadata)


# Fixtures

@pytest.fixture(scope='module', params=configurations)
def get_configuration(request):
    """Get configurations from the module."""
    return request.param


# Functions

def create_files(files, folder, content=b''):
    """Create all the files in the list

    Parameters
    ----------
    files : list
        List of names to create files.
    folder : str
        Directory where the files are being created.
    content : basestring
        Content to write in each file.
    """
    for file in files:
        create_file(REGULAR, folder, file, content=content)


def check_diff(files, folder):
    """Check if the files are duplicated in diff directory

    Parameters
    ----------
    files : list
        List of names to check files.
    folder : str
        Directory where the files are created.
    """
    diff_file = os.path.join(WAZUH_PATH, 'queue', 'diff', 'local')

    if sys.platform == 'win32':
        diff_file = os.path.join(diff_file, 'c')
        diff_file = os.path.join(diff_file, folder.strip('C:\\'))
    else:
        diff_file = os.path.join(diff_file, folder.strip('/'))

    for file in files:
        assert os.path.exists(os.path.join(diff_file, file)), f'{os.path.join(diff_file, file)} does not exist'


def get_size(start_path='.'):
    """Go through a directory and its subdirectories and add the size of each file found.

    Parameters
    ----------
    start_path : str
        Path to get the size.

    Returns
    -------
    total_size : int
        The total size in bytes of all files found.
    """
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)

    return total_size


def calculate_metrics(folder, event_list, fim_mode):
    """Calculate the size of the directory, the creation time of the file list and the time to generate the logs.

    Parameters
    ----------
    folder : str
        Directory where the files are being created
    event_list : list
        List of events from LogMonitor.
    fim_mode : str
        Current monitoring mode.

    Returns
    -------
    size_original_folder : int
        Size of given folder in bytes.
    used_rss_memory : float
        “Resident Set Size”, this is the non-swapped physical memory a process has used.
    used_vms_memory : float
        “Virtual Memory Size”, this is the total amount of virtual memory used by the process.
    total_creation_time : int
        Time needed to create all files in seconds.
    mean : float
        Average time taken to generate each log in seconds.
    median : float
        Median time taken to generate each log in seconds.
    min : int
        Min time taken to generate a log in seconds.
    max : int
        Max time taken to generate a log in seconds.
    """
    size_original_folder = get_size(folder)
    used_rss_memory = process.memory_info().rss / (1024 * 1024)
    used_vms_memory = process.memory_info().vms / (1024 * 1024)
    total_creation_time = event_list[-1]['data']['attributes']['mtime'] - event_list[0]['data']['attributes']['mtime']

    # If scheduled, measure scan time (time from the first to last log), otherwise,
    # measure time from the last file created to the last log generated.
    if fim_mode == 'scheduled':
        elapsed_time_list = [event['data']['timestamp'] - event_list[0]['data']['timestamp'] for event in event_list]
    else:
        elapsed_time_list = [event['data']['timestamp'] - event['data']['attributes']['mtime'] for event in event_list]

    return size_original_folder, used_rss_memory, used_vms_memory, total_creation_time, mean(elapsed_time_list), \
        median(elapsed_time_list), min(elapsed_time_list), max(elapsed_time_list)


def write_csv(data):
    """Create a dataframe and write it in a csv file.

    Parameters
    ----------
    data : list of lists
        Each list is a row of data to write.
    """
    df = pandas.DataFrame(data, columns=['FIM mode', 'Event type', 'N of files', 'Size/file (B)', 'Folder size (B)',
                                         'Size RSS (MB)', 'Sieze VMS (MB)', 'Time to create files (s)',
                                         'Mean time to show logs (s)', 'Median time to show logs (s)',
                                         'Min time to show a log (s)', 'Max time to show a log (s)'])
    if not os.path.exists(metrics_dir):
        os.makedirs(metrics_dir)
    df.to_csv(metrics_path, sep='\t', mode='a', index=False, header=(not os.path.exists(metrics_path)))


@pytest.mark.skip(reason="It will be blocked by #1602, when it was solve we can enable again this test")
@pytest.mark.benchmark
@pytest.mark.parametrize('tags_to_apply', [
    {'ossec_conf'}
])
@pytest.mark.parametrize('n_files', [
    10, 100, 1000, 2000
])
@pytest.mark.parametrize('file_size', [
    0, 1024 * 59
])
def test_report_changes_big(file_size, n_files, tags_to_apply, get_configuration, configure_environment,
                            restart_syscheckd, wait_for_fim_start):
    '''
    description: Check if the 'wazuh-syscheckd' daemon generates the 'diff' files on large amounts of files and
                 files with a large size using the 'report_changes' feature. For this purpose, the test creates
                 in a monitored directory (with the 'report_changes' attribute) large amounts of files and files
                 with large size. Then it checks if the expected number of FIM events is obtained, if they are
                 of the correct type and if a copy of each file has been created in the corresponding directory.
                 In addition, the test generates a CSV file with metrics about the time used to create
                 the files, generate the logs, and the size of the directory.

    wazuh_min_version: 4.2.0

    parameters:
        - file_size:
            type: int
            brief: Size of each testing file in bytes.
        - n_files:
            type: int
            brief: Number of testing files to create.
        - tags_to_apply:
            type: set
            brief: Run test if match with a configuration identifier, skip otherwise.
        - get_configuration:
            type: fixture
            brief: Get configurations from the module.
        - configure_environment:
            type: fixture
            brief: Configure a custom environment for testing.
        - restart_syscheckd:
            type: fixture
            brief: Clear the 'ossec.log' file and start a new monitor.
        - wait_for_fim_start:
            type: fixture
            brief: Wait for realtime start, whodata start, or end of initial FIM scan.

    assertions:
        - Verify that FIM events are generated for each modified file.
        - Verify that for each modified file a 'diff' file is generated.
        - Verify that 'diff' files are updated when files are modified.

    input_description: A test case (ossec_conf) is contained in external YAML file (wazuh_conf.yaml)
                       which includes configuration settings for the 'wazuh-syscheckd' daemon and, it
                       is combined with the testing files to be monitored defined in this module.

    expected_output:
        - r'.*Sending FIM event: (.+)$' ('added', 'modified', and 'deleted' events)
        - A CSV file with the metrics collected.

    tags:
        - scheduled
        - time_travel
    '''
    check_apply_test(tags_to_apply, get_configuration['tags'])
    fim_mode = get_configuration['metadata']['fim_mode']
    data = []

    # Create the list of files
    folder = testdir1
    file_list = [f'regular_{fim_mode}_{n_files}_{i}_{file_size}' for i in range(n_files)]
    create_files(file_list, folder, b'0' * file_size)

    # Get events generated when creating files
    check_time_travel(fim_mode == 'scheduled', monitor=wazuh_log_monitor)
    event_list = wazuh_log_monitor.start(timeout=timeout, callback=callback_detect_event,
                                         accum_results=len(file_list)).result()

    # Assert number of events and type match with expected
    assert len(event_list) == len(file_list), 'Not all files raised an event'
    assert all(event['data']['type'] == 'added' for event in event_list), 'Event type not equal'

    # Check if the files are duplicated in diff path
    check_diff(file_list, folder)

    # Save the metrics to write them in a CSV
    data.append([fim_mode, 'Add', len(file_list), file_size,
                 *calculate_metrics(folder, event_list, fim_mode)])

    # Modify all the files and check if they are still on diff folder
    create_files(file_list, folder, b'1' * file_size)

    # Get events generated when modifying files
    check_time_travel(fim_mode == 'scheduled', monitor=wazuh_log_monitor)
    event_list = wazuh_log_monitor.start(timeout=timeout, callback=callback_detect_event,
                                         accum_results=len(file_list)).result()

    # Assert content_changes tag, number of events and type match with expected
    assert len(event_list) == len(file_list), 'Not all files raised an event'
    assert all(event['data']['type'] == 'modified' for event in event_list), 'Event type not equal'
    assert all(event['data'].get('content_changes') is not None for event in event_list if file_size), \
        f'content_changes is empty'
    check_diff(file_list, folder)

    # Save the metrics to write them in a CSV
    data.append([fim_mode, 'Modify', len(file_list), file_size,
                 *calculate_metrics(folder, event_list, fim_mode)])

    # Write the CSV
    write_csv(data)
