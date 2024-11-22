"""SatNOGS Network functions that consume DB API"""
import requests
from django.conf import settings

DB_API_URL = settings.DB_API_ENDPOINT
DB_API_KEY = settings.DB_API_KEY
DB_API_TIMEOUT = settings.DB_API_TIMEOUT


class DBConnectionError(Exception):
    """Error when there are connection issues with DB API"""


def satnogs_db_api_request_authed(url):
    """Perform authenticated query on SatNOGS DB API and return the results"""
    headers = {}
    if DB_API_KEY:
        headers['authorization'] = 'Token {0}'.format(DB_API_KEY)
    if not DB_API_URL:
        raise DBConnectionError('Error in DB API connection. Blank DB API URL!')
    try:
        request = requests.get(url, headers=headers, timeout=DB_API_TIMEOUT)
        request.raise_for_status()
    except requests.exceptions.RequestException as error:
        raise DBConnectionError('Error in DB API connection. Please try again!') from error
    return request.json()


def get_tle_set_by_sat_id(sat_id):
    """Returns TLE set filtered by Satellite ID"""
    tle_url = "{}tle/?sat_id={}".format(DB_API_URL, sat_id)
    return satnogs_db_api_request_authed(tle_url)


def get_tle_sets():
    """Returns TLE sets"""
    tle_url = "{}tle/".format(DB_API_URL)
    return satnogs_db_api_request_authed(tle_url)


def get_tle_sets_by_sat_id_set(sat_id_set):
    """Returns TLE sets filtered by Satellite ID list"""
    if not sat_id_set:
        raise ValueError('Expected a non empty list of Satellite IDs.')
    if len(sat_id_set) == 1:
        sat_id = next(iter(sat_id_set))
        tle_set = get_tle_set_by_sat_id(sat_id)
        return {sat_id: tle_set}

    tle_sets_list = get_tle_sets()

    tle_sets = {t['sat_id']: [t] for t in tle_sets_list if t['sat_id'] in sat_id_set}
    found_sat_ids_set = set(tle_sets.keys())
    for sat_id in sat_id_set.difference(found_sat_ids_set):
        tle_sets[sat_id] = []
    return tle_sets


def satnogs_db_api_request(url):
    """Perform query on SatNOGS DB API and return the results"""
    if not DB_API_URL:
        raise DBConnectionError('Error in DB API connection. Blank DB API URL!')
    try:
        request = requests.get(url, timeout=DB_API_TIMEOUT)
    except (requests.exceptions.RequestException, requests.exceptions.Timeout) as error:
        raise DBConnectionError('Error in DB API connection. Please try again!') from error
    return request.json()


def get_transmitter_by_uuid(uuid):
    """Returns transmitter filtered by Transmitter UUID"""
    transmitters_url = "{}transmitters/?uuid={}".format(DB_API_URL, uuid)
    return satnogs_db_api_request(transmitters_url)


def get_transmitters_by_sat_id(sat_id):
    """Returns transmitters filtered by Satellite ID"""
    transmitters_url = "{}transmitters/?sat_id={}".format(DB_API_URL, sat_id)
    return satnogs_db_api_request(transmitters_url)


def get_transmitters_by_status(status):
    """Returns transmitters filtered by status"""
    transmitters_url = "{}transmitters/?status={}".format(DB_API_URL, status)
    return satnogs_db_api_request(transmitters_url)


def get_transmitters():
    """Returns all transmitters"""
    transmitters_url = "{}transmitters".format(DB_API_URL)
    return satnogs_db_api_request(transmitters_url)


def get_transmitters_by_uuid_set(uuid_set, raise_error=True):
    """Returns transmitters filtered by Transmitter UUID list"""
    if not uuid_set:
        raise ValueError('Expected a non empty list of UUIDs.')
    if len(uuid_set) == 1:
        transmitter_uuid = next(iter(uuid_set))
        transmitter = get_transmitter_by_uuid(transmitter_uuid)
        if not transmitter and raise_error:
            raise ValueError('Invalid Transmitter UUID: {0}'.format(str(transmitter_uuid)))
        return {transmitter[0]['uuid']: transmitter[0]}

    transmitters_list = get_transmitters()

    transmitters = {t['uuid']: t for t in transmitters_list if t['uuid'] in uuid_set}
    invalid_transmitters = [str(uuid) for uuid in uuid_set.difference(set(transmitters.keys()))]

    if not invalid_transmitters:
        return transmitters

    if len(invalid_transmitters) == 1:
        raise ValueError('Invalid Transmitter UUID: {0}'.format(invalid_transmitters[0]))

    raise ValueError('Invalid Transmitter UUIDs: {0}'.format(invalid_transmitters))


def get_artifact_metadata_by_observation_id(observation_id):
    """Return the artifact metadata for the given observation id"""
    artifacts_url = "{}artifacts/?network_obs_id={}".format(DB_API_URL, observation_id)
    return satnogs_db_api_request_authed(artifacts_url)
