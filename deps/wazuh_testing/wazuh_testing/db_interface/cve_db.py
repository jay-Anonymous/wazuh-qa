from datetime import datetime
from time import sleep
from sqlite3 import OperationalError

from wazuh_testing import CVE_DB_PATH
from wazuh_testing.db_interface import make_sqlite_query, get_sqlite_query_result
from wazuh_testing.modules import vulnerability_detector as vd


def _get_rows_number(cve_table):
    """Get the rows number of a specific table from the CVE database

    Args:
        cve_table (str): CVE table name.

    Returns
        int: Number of rows.
    """
    query_string = f"SELECT count(*) from {cve_table}"
    query_result = get_sqlite_query_result(vd.CVE_DB_PATH, query_string)
    rows_number = int(query_result[0])

    return rows_number


def get_tables():
    """Get all the table names from the CVE database.

    Returns:
        list(str): Table names.
    """
    return get_sqlite_query_result(vd.CVE_DB_PATH, "SELECT name FROM sqlite_master WHERE type='table';")


def clean_table(table):
    """Delete all table entries from CVE DB.

    Args:
        table (str): DB table.
    """
    make_sqlite_query(CVE_DB_PATH, [f"DELETE FROM {table}"])


def clean_all_tables():
    """Clean all tables from CVE database."""
    query = [f"DELETE FROM {table}" for table in get_tables()]

    # Send all queries in the same batch (instead of calling clean_table method) to avoid so many restarts of wazuh-db
    make_sqlite_query(CVE_DB_PATH, query)


def insert_vulnerability(cveid=vd.DEFAULT_VULNERABILITY_ID, target='RHEL7', target_minor='',
                         package=vd.DEFAULT_PACKAGE_NAME, operation='less than', operation_value='2.0.0-1.el7',
                         title='', severity='critical',
                         published=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"), updated='',
                         reference='https://github.com/wazuh/wazuh-qa', target_v='REDHAT', cvss='10.000000',
                         cvss_vector='AV:N/AC:L/Au:N/C:C/I:C/A:C', rationale='Wazuh integration test vulnerability',
                         cvss3='', bugzilla_reference='https://github.com/wazuh/wazuh-qa', cwe='WVE-000 -> WVE-001',
                         advisory='RHSA-2010:0029', ref_target='RHEL'):
    """Insert a vulnerability in CVE database.

    Args:
        cveid (str): Vulnerability ID.
        target (str): OS target.
        target_minor (str): OS target minor version.
        package (str): Package name.
        operation (str): Operation to compare the version of the packages.
        operation_value (str): Value used to compare the packages.
        title (str): Vulnerability title.
        severity (str): Vulnerability severity.
        published (str): Date when the vulnerability was published.
        updated (str): Contain if the package was updated.
        reference (str): URL referencing the vulnerability.
        target_v (str): OS target family.
        cvss (str): Common vulnerability scoring system.
        cvss_vector (str): Representation of the values used to derive the score.
        rationale (str): Reasons to describe the vulnerability.
        cvss3 (str): Common vulnerability scoring system version 3.
        bugzilla_reference (str): URL referencing to bugzilla.
        cwe (str): CWE ID.
        advisory (str): Advisory ID.
        ref_target (str): OS target ID.
    """
    queries = [
        'INSERT INTO VULNERABILITIES (cveid, target, target_minor, package, operation, operation_value) VALUES '
        f"('{cveid}', '{target}', '{target_minor}', '{package}', '{operation}', '{operation_value}')",

        'INSERT INTO VULNERABILITIES_INFO (ID, title, severity, published, updated, target, rationale, cvss, '
        f"cvss_vector, CVSS3, cwe) VALUES ('{cveid}', '{title}', '{severity}', '{published}', '{updated}', "
        f"'{target_v}', {rationale}', '{cvss}', '{cvss_vector}', '{cvss3}', '{cwe}')",

        f"INSERT INTO REFERENCES_INFO (id, target, reference) VALUES ('{cveid}', '{ref_target}', "
        f"'{bugzilla_reference}')",

        f"INSERT INTO BUGZILLA_REFERENCES_INFO (id, target, bugzilla_reference) VALUES ('{cveid}', '{ref_target}', "
        f"'{bugzilla_reference}')",

        f"INSERT INTO ADVISORIES_INFO (id, target, advisory) VALUES ('{cveid}', '{ref_target}', '{advisory}')"
    ]

    make_sqlite_query(vd.CVE_DB_PATH, queries)


def delete_vulnerability(cveid):
    """Remove a vulnerability from the DB.

    Args:
        cveid (str): Vulnerability ID.
    """
    queries = [
        f"DELETE FROM VULNERABILITIES WHERE cveid='{cveid}'",
        f"DELETE FROM VULNERABILITIES_INFO WHERE id='{cveid}'",
        f"DELETE FROM REFERENCES_INFO WHERE id='{cveid}'",
        f"DELETE FROM BUGZILLA_REFERENCES_INFO WHERE id='{cveid}'",
        f"DELETE FROM ADVISORIES_INFO WHERE id='{cveid}'"
    ]

    make_sqlite_query(vd.CVE_DB_PATH, queries)


def get_provider_feeds_number():
    """Get the number of feeds inserted in VULNERABILITIES table of CVE DB.

    Returns:
        int: Total number of feeds in the VULNERABILITIES table.
    """
    return _get_rows_number('VULNERABILITIES')


def get_NVD_feeds_number():
    """Get the number of feeds inserted in NVD_CVE table of CVE DB.

    Returns:
        int: Total number of feeds in the NVD_CVE table.
    """
    return _get_rows_number('NVD_CVE')


def get_MSU_feeds_number():
    """Get the number of feeds inserted in MSU table of CVE DB.

    Returns:
        int: Total number of feeds in the MSU table.
    """
    return _get_rows_number('MSU')


def modify_metadata_vuldet_feed(feed, timestamp):
    """Function to modify the timestamp value of the metadata table for a specific feed.

    Args:
        feed (str): Feed name.
        timestamp (str): Timestamp value to set.
    """
    query_string = f"update METADATA set TIMESTAMP='{timestamp}' where TARGET='{feed}'"
    make_sqlite_query(vd.CVE_DB_PATH, [query_string])
    sleep(1)


def modify_nvd_metadata_vuldet(timestamp):
    """Update the timestamp value of the nvd_metadata table.

    Args:
        timestamp (int): The new timestamp value to set.

    Raises:
        sqlite3.OperationalError: If could not update the value.
    """
    query_string = f"UPDATE NVD_METADATA SET LAST_UPDATE={timestamp};"

    for _ in range(vd.VULN_DETECTOR_GLOBAL_TIMEOUT):
        try:
            make_sqlite_query(vd.CVE_DB_PATH, [query_string])
            break
        except OperationalError:
            sleep(1)
    else:
        raise OperationalError


def check_inserted_value_exists(table, column, value):
    """Function to check if a value exists in a specific column of a specific table.

    Args:
        table (str): Table of cve.db.
        column (str): Column of the table.
        value (str): Value to be checked.
    """
    custom_value = f"'{value}'" if type(value) == str else value
    query_string = f"SELECT count(*) FROM {table} WHERE {column}={custom_value}"
    result = get_sqlite_query_result(vd.CVE_DB_PATH, query_string)
    rows_number = int(result[0])

    return rows_number > 0
