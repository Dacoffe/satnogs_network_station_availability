$(document).ready(function() {
    'use strict';

    // Add current copyright year
    var current_year = '-' + new Date().getFullYear();
    $('#copy').text(current_year);

    // Initialize tooltips
    $('[data-toggle="tooltip"]').tooltip();

    // Make table rows clickable
    $('.clickable-row').click(function(e) {
        if (e.target.nodeName != 'A') {
            var href = $(this).data('href');
            e.preventDefault();
            if (e.ctrlKey) {
                window.open(href, '_blank');
            } else {
                window.location = href;
            }
        }
    });
});
