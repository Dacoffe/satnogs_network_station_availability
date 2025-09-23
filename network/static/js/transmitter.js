$(document).ready(transmitter_params_modal);
document.addEventListener('obs_changed', transmitter_params_modal, false);

function transmitter_params_modal() {
    'use strict';

    $('#TransmitterParamsModal').on('show.bs.modal', function (event) {
        var button = $(event.relatedTarget);
        const observation_id = button.data('observation-id');
        var modal = $(this);

        modal.find('.front-data').text('-');
        modal.find('#param-status').removeClass('badge-success badge-danger').addClass('badge-secondary').text('-');
        modal.find('#param-raw-json').hide();
        modal.find('#toggle-raw-json').text('Show Raw JSON');

        $.ajax({
            url: '/api/observations/' + observation_id + '/'
        }).done(function (data) {
            var params = data.transmitter_parameters;

            if (!params || Object.keys(params).length === 0) {
                modal.find('.modal-body').html('<div class="card"><div class="card-body"><p class="text-center text-muted">No transmitter parameters available</p></div></div>');
                return;
            }

            modal.find('#param-uuid').text(params.uuid || '-');
            modal.find('#param-description').text(params.description || '-');
            modal.find('#param-type').text(params.type || '-');


            if (params.alive === true) {
                modal.find('#param-status').removeClass('badge-secondary badge-danger').addClass('badge-success').text('Active');
            } else if (params.alive === false) {
                modal.find('#param-status').removeClass('badge-secondary badge-success').addClass('badge-danger').text('Inactive');
            } else {
                modal.find('#param-status').text('Unknown');
            }

            if (params.downlink_low) {
                modal.find('#param-downlink-low').text((params.downlink_low / 1000000).toFixed(3) + ' MHz');
            }
            if (params.downlink_high) {
                modal.find('#param-downlink-high').text((params.downlink_high / 1000000).toFixed(3) + ' MHz');
            }
            if (params.uplink_low) {
                modal.find('#param-uplink-low').text((params.uplink_low / 1000000).toFixed(3) + ' MHz');
            } else {
                modal.find('#param-uplink-low').text('N/A');
            }
            if (params.uplink_high) {
                modal.find('#param-uplink-high').text((params.uplink_high / 1000000).toFixed(3) + ' MHz');
            } else {
                modal.find('#param-uplink-high').text('N/A');
            }

            modal.find('#param-mode').text(params.mode || '-');
            modal.find('#param-baud').text(params.baud ? params.baud + ' baud' : '-');
            modal.find('#param-invert').text(params.invert ? 'Yes' : 'No');

            modal.find('#param-service').text(params.service || '-');
            modal.find('#param-satellite').text(params.satellite || data.norad_cat_id || '-');

            if (params.updated) {
                var date = new Date(params.updated);
                modal.find('#param-updated').text(date.toLocaleDateString() + ' ' + date.toLocaleTimeString());
            }

        }).fail(function() {
            modal.find('.modal-body').html('<div class="card"><div class="card-body"><p class="text-center text-danger">Failed to load transmitter parameters</p></div></div>');
        });
    });
}
