"""SatNOGS Network base permissions"""


class UserNoPermissionError(Exception):
    """Error when user has not persmission"""


def has_perm_to_schedule_violator(user):
    """
    Determines whether the user can schedule violator satellites
    for stations that allow it (violator_scheduling='Only Operators')
    """
    return user.is_authenticated and user.groups.filter(name='Operators').exists()


def raise_permission_errors_for_stations(stations_perms):
    """
    Check if in the given dictionary of scheduling permissions per station, there are stations that
    don\'t have scheduling permissions.
    """
    stations_without_permissions = [
        int(station_id) for station_id in stations_perms.keys() if not stations_perms[station_id]
    ]
    if stations_without_permissions:
        if len(stations_without_permissions) == 1:
            raise UserNoPermissionError(
                'No permission to schedule observations on station: '
                f'{stations_without_permissions[0]}'
            )
        raise UserNoPermissionError(
            f'No permission to schedule observations on stations: {stations_without_permissions}'
        )


def has_perm_to_schedule_violators_on_station(user, station):
    """
    This context flag will determine if user can schedule satellites that violate frequencies on
    the given station.
    """
    if not user.is_authenticated:
        return False
    if station.violator_scheduling > 0:
        if station.violator_scheduling == 2 or has_perm_to_schedule_violator(user):
            return True
    return False


def has_perm_to_schedule_violators_on_stations(user, stations):
    """
    This context flag will determine if user can schedule satellites that violate frequencies on
    the given stations.
    """
    if not user.is_authenticated:
        return {station.id: False for station in stations}
    return {
        station.id: has_perm_to_schedule_violators_on_station(user, station)
        for station in stations
    }


def check_schedule_perms_of_violators_per_station(user, station_set):
    """Checks if user has permissions to schedule on stations"""
    stations_perms = has_perm_to_schedule_violators_on_stations(user, station_set)
    raise_permission_errors_for_stations(stations_perms)


def has_schedule_perms(user):
    """
    This context flag will determine if user can schedule an observation.
    That includes station owners, moderators, operators, admins.
    see: https://wiki.satnogs.org/Operation#Network_permissions_matrix
    """
    if not user.is_authenticated:
        return False
    if user.groups.filter(name='Moderators').exists():
        return True
    if user.groups.filter(name='Operators').exists():
        return True
    if user.is_superuser:
        return True
    if user.connected_stations.exists():
        return True
    return False


def get_scheduling_user_attributes(user):
    """
    Returns the user's attributes that determine their scheduling perms
    """
    is_authenticated = user.is_authenticated
    if not is_authenticated:
        return (False, ) * 5
    is_superuser = user.is_superuser
    is_moderator = user.groups.filter(name="Moderators").exists()
    is_operator = user.groups.filter(name="Operators").exists()
    has_useable_non_testing_stations = user.useable_stations.filter(testing=False).exists()

    return (
        is_authenticated, is_superuser, is_moderator, is_operator, has_useable_non_testing_stations
    )


def has_perm_to_schedule_on_station(
    user,
    target_station,
    is_authenticated=None,
    is_superuser=None,
    is_moderator=None,
    is_operator=None,
    has_useable_non_testing_stations=None
):
    """
    This context flag will determine if user can schedule an observation on the passed station
    That includes station owners, moderators, operators, admins.
    see: https://wiki.satnogs.org/Operation#Network_permissions_matrix
    """
    if all(attr is None for attr in (is_authenticated, is_superuser, is_moderator, is_operator,
                                     has_useable_non_testing_stations)):
        (
            is_authenticated, is_superuser, is_moderator, is_operator,
            has_useable_non_testing_stations
        ) = get_scheduling_user_attributes(user)

    if not is_authenticated:
        return False
    if is_superuser or is_moderator:
        return True
    if target_station.owner == user:
        return True

    # Useable stations refer to connected, available stations
    # with set longitude, latitude and altitude
    if has_useable_non_testing_stations or is_operator:
        return target_station.is_available

    return False


def get_schedule_permissions_per_station(user, stations):
    """
    This context flag will determine if user can schedule an observation.
    That includes station owners, moderators, admins.
    see: https://wiki.satnogs.org/Operation#Network_permissions_matrix

     @param: user The user that schedules the observations
     @param: stations All connected stations that have non-null lat, lng and alt
    """

    user_attrs = get_scheduling_user_attributes(user)
    return {
        station.id: get_schedule_permissions_per_station(user, station, *user_attrs)
        for station in stations
    }


def check_schedule_perms_per_station(user, station_set):
    """Checks if user has permissions to schedule on stations"""
    stations_perms = get_schedule_permissions_per_station(user, station_set)
    raise_permission_errors_for_stations(stations_perms)


def has_delete_obs_perms(user, observation):
    """
    This context flag will determine if a delete button appears for the observation.
    That includes observer, station owner involved, moderators, admins.
    see: https://wiki.satnogs.org/Operation#Network_permissions_matrix
    """
    if observation.is_started or not user.is_authenticated:
        return False
    # User owns the observation
    if observation.author == user:
        return True
    # User owns the station
    if observation.ground_station and observation.ground_station.owner == user:
        return True
    # User has special permissions
    if user.groups.filter(name='Moderators').exists():
        return True
    if user.is_superuser:
        return True
    return False


def has_vet_perms(user, observation):
    """
    This context flag will determine if vet buttons appears for the observation.
    That includes observer, station owner involved, moderators, admins.
    see: https://wiki.satnogs.org/Operation#Network_permissions_matrix
    """
    if not user.is_authenticated:
        return False

    # User has connected, available non-testing station
    if user.useable_stations.filter(testing=False).exists():
        return True

    # User owns the observation
    # Users can vet if they have a station that
    # has connected at least once (non-future station)
    if observation.author == user and user.ground_stations.filter(last_seen__isnull=False
                                                                  ).exists():
        return True

    # User owns the station
    if observation.ground_station and observation.ground_station.owner == user:
        return True

    # User has special permissions
    if user.groups.filter(name='Moderators').exists() or user.groups.filter(
            name='Operators').exists() or user.is_superuser or user.has_perm('base.can_vet'):
        return True
    return False


def modify_delete_station_perms(user, station):
    """
    This context flag will determine if the user can modify or delete a station
    or bulk-delete future observations on a station.
    That includes station owners, moderators and admins.
    """
    if not user.is_authenticated:
        return False

    # User owns the station
    if user == station.owner:
        return True

    # User has special permissions
    if user.groups.filter(name='Moderators').exists():
        return True
    if user.is_superuser:
        return True
    return False
