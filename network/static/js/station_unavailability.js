/* global moment tempusDominus */

$(document).ready(function() {
    'use strict';

    // On the "Add Ground Station" page the unavailability section is hidden (it requires an
    // existing station pk). Guard early so we don't crash on missing DOM elements, but still
    // define window.appendUnavailabilityPeriods with empty management form fields so the
    // station form POST doesn't trigger a Django "ManagementForm data is missing" error.
    if (!document.getElementById('unavailability-datetimepicker-start')) {
        window.appendUnavailabilityPeriods = function(form) {
            form.append('<input type="hidden" name="unavail-TOTAL_FORMS" value="0">');
            form.append('<input type="hidden" name="unavail-INITIAL_FORMS" value="0">');
            form.append('<input type="hidden" name="unavail-MAX_NUM_FORMS" value="1000">');
        };
        return;
    }

    var DISPLAY_FORMAT = 'YYYY-MM-DD HH:mm';
    var SUBMIT_FORMAT = 'YYYY-MM-DD HH:mm:ss';

    // Parse and initialize unavailability period data and remove the html elements holding them
    var periods_element = $('#unavailability-data-to-parse');
    var periods = [];
    var current_order = -1;

    periods_element.children().each(function() {
        var period_data = $(this).data();
        // The edit table only manages editable (future/ongoing) periods. That filtering is now
        // done on the backend (BaseStationUnavailabilityPeriodInlineFormSet.get_queryset filters
        // end > now), so every period rendered here is already editable; past periods are not
        // rendered and are left untouched on save (they stay visible on the station page).
        // All datetimes here are UTC (the fields are labelled "(UTC)" and the backend interprets
        // the submitted naive datetimes as UTC), so the rest of this file parses/compares in UTC
        // like observation_new.js.
        var period = {
            'start': String(period_data.start),
            'end': String(period_data.end),
            'initial': Object.prototype.hasOwnProperty.call(period_data, 'id'),
            'deleted': false
        };
        if (period.initial) {
            period.id = period_data.id;
        }
        periods.push(period);
    });
    periods_element.remove();

    // Initialize the datetime pickers (same library/config as the observation pages)
    var date_configuration = {
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
            format: 'yyyy-MM-dd HH:mm',
            hourCycle: 'h23'
        }
    };
    var start_picker = new tempusDominus.TempusDominus(
        document.getElementById('unavailability-datetimepicker-start'), date_configuration
    );
    var end_picker = new tempusDominus.TempusDominus(
        document.getElementById('unavailability-datetimepicker-end'), date_configuration
    );

    function get_start_value() {
        return $('#unavailability-datetimepicker-start input').val();
    }

    function get_end_value() {
        return $('#unavailability-datetimepicker-end input').val();
    }

    function human_duration(start, end) {
        var milliseconds = moment(end, DISPLAY_FORMAT).diff(moment(start, DISPLAY_FORMAT));
        if (milliseconds <= 0) {
            return '-';
        }
        return moment.duration(milliseconds).humanize();
    }

    // Render the table of periods from the in-memory array
    function update_periods_table() {
        var tbody = $('#unavailability-table tbody');
        tbody.empty();
        var visible = 0;
        periods.forEach(function(period, order) {
            if (period.deleted) {
                return;
            }
            visible++;
            var row = '<tr>' +
                '<td>' + period.start + '</td>' +
                '<td>' + period.end + '</td>' +
                '<td>' + human_duration(period.start, period.end) + '</td>' +
                '<td class="text-right">' +
                '<button type="button" class="btn btn-sm btn-primary" data-action="edit" ' +
                'data-order="' + order + '" data-toggle="modal" data-target="#unavailability-modal">' +
                '<span class="bi bi-pencil-square" aria-hidden="true"></span> Edit</button>' +
                '</td></tr>';
            tbody.append(row);
        });
        if (visible === 0) {
            tbody.append(
                '<tr><td colspan="4" class="text-center text-muted">' +
                'No unavailability periods defined.</td></tr>'
            );
        }
    }
    update_periods_table();

    // Validate the modal inputs, show errors and toggle the Save Period button accordingly
    function validate_period() {
        var save_button = $('#unavailability-modal button[data-action=save]');
        var error_container = $('#unavailability-modal-errors');
        var errors = [];

        var start_value = get_start_value();
        var end_value = get_end_value();
        // The picker fields hold UTC wall-clock times (labelled "(UTC)"), and the backend
        // interprets the submitted naive datetimes as UTC. Parse and compare everything in UTC so
        // the "in the future" check matches the server, regardless of the browser's timezone.
        var start = moment.utc(start_value, DISPLAY_FORMAT, true);
        var end = moment.utc(end_value, DISPLAY_FORMAT, true);

        if (!start_value || !end_value || !start.isValid() || !end.isValid()) {
            errors.push('Both a valid start and end datetime are required.');
        } else {
            if (start >= end) {
                errors.push('Start datetime should be before end datetime.');
            }
            // Future-only validation (like observation scheduling). The end must always be in the
            // future, so a period cannot be entirely in the past. The start must be in the future
            // only for NEW periods (current_order < 0); existing periods may already be ongoing
            // (start in the past, end in the future) and must remain editable.
            var now = moment.utc();
            if (end.isBefore(now)) {
                errors.push('End datetime should be in the future.');
            }
            if (current_order < 0 && start.isBefore(now)) {
                errors.push('Start datetime should be in the future.');
            }
            periods.forEach(function(period, order) {
                if (period.deleted || order === current_order) {
                    return;
                }
                var other_start = moment.utc(period.start, DISPLAY_FORMAT);
                var other_end = moment.utc(period.end, DISPLAY_FORMAT);
                if (start < other_end && end > other_start) {
                    errors.push(
                        'Period overlaps with an existing one (' + period.start + ' - ' +
                        period.end + ').'
                    );
                }
            });
        }

        if (errors.length) {
            error_container.html(errors.join('<br>')).show();
            save_button.prop('disabled', true);
            return false;
        }
        error_container.hide().empty();
        save_button.prop('disabled', false);
        return true;
    }

    // TempusDominus fires its change event BEFORE it writes the new value into the <input>, so
    // reading the input synchronously here would validate against the previous value. Defer to the
    // next tick so validate_period() sees the updated input value. To allow for more responsive form.
    function validate_period_deferred() {
        setTimeout(validate_period, 0);
    }
    start_picker.subscribe(tempusDominus.Namespace.events.change, validate_period_deferred);
    end_picker.subscribe(tempusDominus.Namespace.events.change, validate_period_deferred);

    // Also re-validate on direct input/change of the datetime fields: the TempusDominus change
    // event does not fire when the user types into the input, which would otherwise leave the
    // Save Period button stuck disabled after a failed save attempt.
    $('#unavailability-modal').on('input change', '.datetimepicker input', function() {
        validate_period();
    });

    // Configure the modal when it is opened from a New Period or Edit button
    $('#unavailability-modal').on('show.bs.modal', function(e) {
        $('#submit').prop('disabled', true);
        var action = $(e.relatedTarget).data('action');
        if (action === 'edit') {
            current_order = $(e.relatedTarget).data('order');
            $('#UnavailabilityModalTitle').text('Edit Period');
            start_picker.dates.setFromInput(periods[current_order].start);
            end_picker.dates.setFromInput(periods[current_order].end);
            $('#unavailability-delete').show();
        } else {
            current_order = -1;
            $('#UnavailabilityModalTitle').text('New Period');
            start_picker.clear();
            end_picker.clear();
            $('#unavailability-delete').hide();
        }
        validate_period();
    });

    // Handle Save Period and Delete actions inside the modal
    $('#unavailability-modal').on('click', '.modal-action', function(e) {
        var action = $(e.currentTarget).data('action');
        if (action === 'save') {
            if (!validate_period()) {
                return;
            }
            var start = moment(get_start_value(), DISPLAY_FORMAT).format(DISPLAY_FORMAT);
            var end = moment(get_end_value(), DISPLAY_FORMAT).format(DISPLAY_FORMAT);
            if (current_order >= 0) {
                periods[current_order].start = start;
                periods[current_order].end = end;
            } else {
                periods.push({'start': start, 'end': end, 'initial': false, 'deleted': false});
            }
        } else if (action === 'delete' && current_order >= 0) {
            if (periods[current_order].initial) {
                periods[current_order].deleted = true;
            } else {
                periods.splice(current_order, 1);
            }
        }
        update_periods_table();
        $('#unavailability-modal').modal('hide');
    });

    $('#unavailability-modal').on('hidden.bs.modal', function() {
        current_order = -1;
        // Only re-enable if the station form is actually valid. Don't assume it's valid just
        // because the modal closed. This respects the form's actual state: invalid → disabled,
        // valid → enabled. Prevents the button from incorrectly becoming enabled when the station
        // form has errors (e.g., blank name, invalid config). If you get out of period modal it won't enable save changes it shouldn't.
        $('#submit').prop('disabled', !$('form')[0].checkValidity());
    });

    // Disable submitting the station form when hitting enter on the date inputs
    $(document).on('keypress', '#unavailability-modal .datetimepicker input', function(e) {
        var code = e.keyCode || e.which;
        if (code === 13) {
            e.preventDefault();
            return false;
        }
    });

    // Serialize the periods into Django inline formset fields on station form submit.
    // Called from prepareAndSubmitForm in station_edit.js.
    window.appendUnavailabilityPeriods = function(form) {
        var total = 0;
        var initial = 0;
        periods.forEach(function(period, order) {
            var prefix = 'unavail-' + order;
            total++;
            if (period.initial) {
                initial++;
                form.append(
                    '<input type="hidden" name="' + prefix + '-id" value="' + period.id + '">'
                );
            }
            if (period.deleted) {
                form.append(
                    '<input type="checkbox" name="' + prefix +
                    '-DELETE" style="display: none" checked>'
                );
            }
            form.append(
                '<input type="hidden" name="' + prefix + '-start" value="' +
                moment(period.start, DISPLAY_FORMAT).format(SUBMIT_FORMAT) + '">'
            );
            form.append(
                '<input type="hidden" name="' + prefix + '-end" value="' +
                moment(period.end, DISPLAY_FORMAT).format(SUBMIT_FORMAT) + '">'
            );
        });
        form.append('<input type="hidden" name="unavail-TOTAL_FORMS" value="' + total + '">');
        form.append('<input type="hidden" name="unavail-INITIAL_FORMS" value="' + initial + '">');
        form.append('<input type="hidden" name="unavail-MAX_NUM_FORMS" value="1000">');
    };
});
