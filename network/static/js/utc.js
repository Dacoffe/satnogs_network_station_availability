/* global moment */

$(document).ready(function() {
    'use strict';
    var local = moment().format('HH:mm');
    var utc = moment().utc().format('HH:mm');
    document.getElementById('timezone-info').title = '  UTC Time: '+ utc + '\nLocal Time: ' + local;
});
