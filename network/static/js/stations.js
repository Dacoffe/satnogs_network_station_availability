/* jshint esversion: 6 */

$(document).ready(function () {
    'use strict';

    // Check if filters should be displayed
    if (window.location.hash == '#collapseFilters') {
        $('#collapseFilters').hide();
    } else if ($('#collapseFilters').data('filtered') == 'True') {
        $('#collapseFilters').show();
    }

    $('.filter-section #status-selector input').click(function() {
        var input = $(this);

        if (input.prop('checked')) {
            input.parent().addClass('btn-inactive');
        } else {
            input.parent().removeClass('btn-inactive');
        }
    });

    const filter_button = $('#filter-button');
    const frequency_formgroup = $('#frequency-filter-formgroup');
    const freq_input = $('#frequency-filter');
    const freq_format = $('#freq-format');

    var initial_freq_val = freq_input.val();
    if(initial_freq_val) {
        freq_format.html(format_frequency(parseInt(initial_freq_val)));
    }

    freq_input.on('input', function(e) {
        e.stopPropagation();
        e.stopImmediatePropagation();
        var has_error = 0;
        var val = parseInt($(this).val());
        const frequency_errors = { '1': 'Value is not a number.', '2': 'Value cannot be less than 0.'};

        if (isNaN(val)) {
            has_error = 1;
        }
        else if (val < 0) {
            has_error = 2;
        }

        if(!val && $(this)[0].validity.valid) {
            frequency_formgroup.removeClass('has-error');
            filter_button.prop('disabled', false);
            freq_format.removeClass('alert-error');
            freq_format.html('');
        }
        else if(!has_error) {
            frequency_formgroup.removeClass('has-error');
            filter_button.prop('disabled', false);
            freq_format.removeClass('alert-error');
            freq_format.html(format_frequency(val));
        } else {
            frequency_formgroup.addClass('has-error');
            filter_button.prop('disabled', true);
            freq_format.addClass('alert-error');
            freq_format.html(frequency_errors[has_error]);
        }
    });
});

function format_frequency(val) {
    if (!Number.isInteger(val)) {
        return 'Error';
    }

    if (val === 0) {
        return '0';
    }

    const unit_table = ['Hz', 'kHz', 'MHz', 'GHz'];
    const div = Math.floor(Math.log10(val) / 3);
    const unit = unit_table[(div > 3) ? 3 : div];

    return val / (Math.pow(1000, (div > 3) ? 3 : div)) + ' ' + unit;
}
