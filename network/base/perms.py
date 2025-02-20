"""SatNOGS Network base permissions"""
from django.core.exceptions import ObjectDoesNotExist


class UserNoPermissionError(Exception):
    """Error when user has not persmission"""


def check_stations_without_permissions(stations_perms):
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
                'No permission to schedule observations on station: {0}'.format(
                    stations_without_permissions[0]
                )
            )
        raise UserNoPermissionError(
            'No permission to schedule observations on stations: {0}'.
            format(stations_without_permissions)
        )


def schedule_station_violators_perms(user, station):
    """
    This context flag will determine if user can schedule satellites that violate frequencies on
    the given station.
    """
    if user.is_authenticated:
        if station.violator_scheduling > 0:
            if station.violator_scheduling == 2 or user.groups.filter(name='Operators').exists():
                return True

    return False


def schedule_stations_violators_perms(user, stations):
    """
    This context flag will determine if user can schedule satellites that violate frequencies on
    the given stations.
    """
    if user.is_authenticated:
        return {
            station.id: schedule_station_violators_perms(user, station)
            for station in stations
        }

    return {station.id: False for station in stations}


def check_schedule_perms_of_violators_per_station(user, station_set):
    """Checks if user has permissions to schedule on stations"""
    stations_perms = schedule_stations_violators_perms(user, station_set)
    check_stations_without_permissions(stations_perms)


def schedule_perms(user):
    """
    This context flag will determine if user can schedule an observation.
    That includes station owners, moderators, admins.
    see: https://wiki.satnogs.org/Operation#Network_permissions_matrix
    """
    if user.is_authenticated:
        # User has special permissions
        if user.groups.filter(name='Moderators').exists():
            return True
        if user.is_superuser:
            return True
        if user.useable_stations.exists():
            return True

    return False


def schedule_station_perms(user, station):
    """
    This context flag will determine if user can schedule an observation.
    That includes station owners, moderators, admins.
    see: https://wiki.satnogs.org/Operation#Network_permissions_matrix
    """
    if user.is_authenticated:
        if station.lat is None or station.lng is None or station.alt is None:
            return False

        # User has connected and available station and the station is connected and available
        try:
            if user.useable_stations.exists() and station.is_connected and station.is_available:
                return True
        except ObjectDoesNotExist:
            pass
        # If the station is unavailable and user is its owner
        if station.is_connected and station.owner == user:
            return True
        # User has special permissions
        if user.groups.filter(name='Moderators').exists():
            return True
        if user.is_superuser:
            return True

    return False


def schedule_stations_perms(user, stations):
    """
    This context flag will determine if user can schedule an observation.
    That includes station owners, moderators, admins.
    see: https://wiki.satnogs.org/Operation#Network_permissions_matrix

     @param: user The user that schedules the observations
     @param: stations All connected stations that have non-null lat, lng and alt
    """
    if user.is_authenticated:
        # User has special permissions
        if user.groups.filter(name='Moderators').exists():
            return {station.id: True for station in stations}
        if user.is_superuser:
            return {station.id: True for station in stations}
        # User has connected and available station and station to schedule is available
        try:
            if user.useable_stations.exists():
                return {s.id: s.owner == user or s.is_available for s in stations}

        except ObjectDoesNotExist:
            pass
        # If the station is unavailable and user is its owner
        return {station.id: station.owner == user for station in stations}

    return {station.id: False for station in stations}


def check_schedule_perms_per_station(user, station_set):
    """Checks if user has permissions to schedule on stations"""
    stations_perms = schedule_stations_perms(user, station_set)
    check_stations_without_permissions(stations_perms)


def delete_perms(user, observation):
    """
    This context flag will determine if a delete button appears for the observation.
    That includes observer, station owner involved, moderators, admins.
    see: https://wiki.satnogs.org/Operation#Network_permissions_matrix
    """
    if not observation.is_started and user.is_authenticated:
        # User owns the observation
        try:
            if observation.author == user:
                return True
        except AttributeError:
            pass
        # User owns the station
        try:
            if observation.ground_station and observation.ground_station.owner == user:
                return True
        except (AttributeError, ObjectDoesNotExist):
            pass
        # User has special permissions
        if user.groups.filter(name='Moderators').exists():
            return True
        if user.is_superuser:
            return True
    return False


def vet_perms(user, observation):
    """
    This context flag will determine if vet buttons appears for the observation.
    That includes observer, station owner involved, moderators, admins.
    see: https://wiki.satnogs.org/Operation#Network_permissions_matrix
    """
    if user.is_authenticated:
        # User has connected and available station
        if user.useable_stations.exists():
            return True
        # User owns the observation
        try:
            if observation.author == user:
                return True
        except AttributeError:
            pass
        # User owns the station
        try:
            if observation.ground_station and observation.ground_station.owner == user:
                return True
        except AttributeError:
            pass
        # User has special permissions
        if user.groups.filter(name='Moderators'
                              ).exists() or user.is_superuser or user.has_perm('base.can_vet'):
            return True
    return False


def modify_delete_station_perms(user, station):
    """
    This context flag will determine if the user can modify or delete a station
    or bulk-delete future observations on a station.
    That includes station owners, moderators and admins.
    """
    if user.is_authenticated:
        # User owns the station
        try:
            if user == station.owner:
                return True
        except AttributeError:
            pass
        # User has special permissions
        if user.groups.filter(name='Moderators').exists():
            return True
        if user.is_superuser:
            return True
    return False
