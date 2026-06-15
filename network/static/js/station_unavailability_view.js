/* global moment */

$(document).ready(function() {
    'use strict';

    var DISPLAY_FORMAT = 'YYYY-MM-DD HH:mm';

    // Fill the Duration column of the Station Unavailability table with a human readable
    // duration, using the same library/formatting as the station edit page.
    $('.unavailability-duration').each(function() {
        var cell = $(this);
        var start = moment(String(cell.data('start')), DISPLAY_FORMAT);
        var end = moment(String(cell.data('end')), DISPLAY_FORMAT);
        if (start.isValid() && end.isValid() && end.diff(start) > 0) {
            cell.text(moment.duration(end.diff(start)).humanize());
        } else {
            cell.text('-');
        }
    });
});
