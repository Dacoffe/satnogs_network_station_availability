/* jshint esversion: 6 */

$(document).ready(function () {
    'use strict';

    // Check if filters should be displayed
    if (window.location.hash == '#collapseFilters') {
        $('#collapseFilters').hide();
    } else if ($('#collapseFilters').data('filtered') == 'True') {
        $('#collapseFilters').show();
    }

    $('.filter-section #status-selector label').click(function () {
        var checkbox = $(this);
        var input = checkbox.find('input[type="checkbox"]');

        if (input.prop('checked')) {
            checkbox.removeClass('btn-inactive');
        } else {
            checkbox.addClass('btn-inactive');
        }
    });


});
