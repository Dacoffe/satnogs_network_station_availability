/* global moment tempusDominus */

$(document).ready(function() {
    'use strict';

    tempusDominus.extend(window.tempusDominus.plugins.customDateFormat);
    var dateConfiguration = {
        useCurrent: false,
        display: {
            icons: {
                type: 'icons',
                time: 'bi bi-clock',
                date: 'bi bi-calendar3',
                up: 'bi bi-arrow-up',
                down: 'bi bi-arrow-down',
                previous: 'bi bi-chevron-left',
                next: 'bi bi-chevron-right',
                today: 'bi bi-calendar-check',
                clear: 'bi bi-trash',
                close: 'bi bi-x-lg'
            },
            sideBySide: true,
            components: {
                useTwentyfourHour: true
            },
            buttons: {
                close: true
            }
        },
        localization: {
            format: 'yyyy-MM-dd HH:mm'
        }
    };
    var start = new tempusDominus.TempusDominus(document.getElementById('datetimepicker-start'), dateConfiguration);
    var end = new tempusDominus.TempusDominus(document.getElementById('datetimepicker-end'), dateConfiguration);

    const otherValidFormats = [
        'YYYY-MM-DD H:mm', 'YYYY-MM-DD HH', 'YYYY-MM-DD H', 'YYYY-MM-DD HH:m',
        'YYYY-MM-DD H:m', 'YYYY-MM-D HH:mm', 'YYYY-MM-D H:mm', 'YYYY-MM-D HH',
        'YYYY-MM-D H', 'YYYY-MM-D HH:m', 'YYYY-MM-D H:m', 'YYYY-M-D HH:mm', 'YYYY-M-D H:mm',
        'YYYY-M-D HH', 'YYYY-M-D H', 'YYYY-M-D HH:m', 'YYYY-M-D H:m', 'YYYY-M-DD HH:mm',
        'YYYY-M-DD H:mm', 'YYYY-M-DD HH', 'YYYY-M-DD H', 'YYYY-M-DD HH:m', 'YYYY-M-DD H:m'
    ];
    $('#datetimepicker-start input').on('blur', function () {
        if (!moment(this.value, 'YYYY-MM-DD HH:mm', true).isValid()){
            var date = moment(this.value, otherValidFormats, true);
            if (date.isValid()){
                var newDate = date.format('YYYY-MM-DD HH:mm');
                start.dates.setFromInput(newDate);
            } else {
                start.clear();
            }
        }
    });
    $('#datetimepicker-end input').on('blur', function () {
        if (!moment(this.value, 'YYYY-MM-DD HH:mm', true).isValid()){
            var date = moment(this.value, otherValidFormats, true);
            if (date.isValid()){
                var newDate = date.format('YYYY-MM-DD HH:mm');
                end.dates.setFromInput(newDate);
            } else {
                end.clear();
            }
        }
    });
    start.subscribe(tempusDominus.Namespace.events.error, (e) => {
        if(e.oldDate){
            var oldDateFormatted = moment(e.oldDate).format('YYYY-MM-DD HH:mm');
            start.dates.setFromInput(oldDateFormatted);
        } else {
            start.clear();
        }
    });
    end.subscribe(tempusDominus.Namespace.events.error, (e) => {
        if(e.oldDate){
            var oldDateFormatted = moment(e.oldDate).format('YYYY-MM-DD HH:mm');
            end.dates.setFromInput(oldDateFormatted);
        } else {
            end.clear();
        }
    });
    start.subscribe(tempusDominus.Namespace.events.change, (e) => {
        if (e.date){
            var newMinEndDate = moment(e.date);
            var newMinEndDateFormatted = newMinEndDate.format('YYYY-MM-DD HH:mm');
            if (end.dates.lastPicked && moment(end.dates.lastPicked) < newMinEndDate) {
                end.dates.setFromInput(newMinEndDateFormatted);
            }
            end.updateOptions({
                restrictions: {minDate: newMinEndDateFormatted},
                localization: {format: 'yyyy-MM-dd HH:mm'}
            });
        } else {
            end.updateOptions(dateConfiguration, true);
        }
    });
    end.subscribe(tempusDominus.Namespace.events.change, (e) => {
        if (e.date){
            var newMaxStartDate = moment(e.date);
            var newMaxStartDateFormatted = newMaxStartDate.format('YYYY-MM-DD HH:mm');
            if (start.dates.lastPicked && moment(start.dates.lastPicked) > newMaxStartDate) {
                start.dates.setFromInput(newMaxStartDateFormatted);
            }
            start.updateOptions({
                restrictions: {maxDate: newMaxStartDateFormatted},
                localization: {format: 'yyyy-MM-dd HH:mm'}
            });
        } else {
            start.updateOptions(dateConfiguration, true);
        }
    });

    var start_value = $('#datetimepicker-start').data('value');
    var end_value = $('#datetimepicker-end').data('value');
    if (start_value){
        start.dates.setFromInput(moment(start_value).format('YYYY-MM-DD HH:mm'));
    }
    if (end_value){
        end.dates.setFromInput(moment(end_value).format('YYYY-MM-DD HH:mm'));
    }

    $('.selectpicker').selectpicker();


    $('.filter-section #status-selector input').click(function() {
        var input = $(this);

        if (input.prop('checked')) {
            input.parent().addClass('btn-inactive');
        } else {
            input.parent().removeClass('btn-inactive');
        }
    });

    // Check if filters should be displayed
    if (window.location.hash == '#collapseFilters') {
        $('#collapseFilters').collapse('hide');
    } else if ($('#collapseFilters').data('filtered') == 'True') {
        $('#collapseFilters').collapse('show');
    }

    // Open all observations in new tabs
    $('#open-all').click(function() {
        $('a.obs-link').each(function() {
            window.open($(this).attr('href'));
        });
    });

    // Open all observations in new tabs with "Shift + A"
    $(document).bind('keyup', function(event){
        if (event.shiftKey && (event.which == 97 || event.which == 65)) {
            $('#open-all').click();
        }
    });

    // Disable submitting form when hiting enter on date inputs
    $(document).on('keypress', '.datetimepicker input', function (e) {
        var code = e.keyCode || e.which;
        if (code == 13) {
            e.preventDefault();
            return false;
        }
    });
});
