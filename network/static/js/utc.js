/* global moment */

$(document).ready(function() {
    'use strict';
    utc_info();
});

document.addEventListener('obs_changed', utc_info, false);

function utc_info() {
    var local = moment().format('HH:mm');
    var utc = moment().utc().format('HH:mm');
    document.getElementById('timezone-info').title = '  UTC Time: '+ utc + '\nLocal Time: ' + local;
}