$(document).ready(vetting_modal);
document.addEventListener('obs_changed', vetting_modal, false);

function vetting_modal() {
    'use strict';

    $('#VettingModal').on('show.bs.modal', function (event) {
        var button = $(event.relatedTarget);
        const observation_id = button.data('observation-id');
        var modal = $(this);

        // Reset modal
        modal.find('#vetting-total').text('-');
        modal.find('#vetting-good-count').text('-');
        modal.find('#vetting-bad-count').text('-');
        modal.find('#vetting-unknown-count').text('-');
        modal.find('#vetting-good-percent').text('-%');
        modal.find('#vetting-bad-percent').text('-%');
        modal.find('#vetting-unknown-percent').text('-%');
        modal.find('#vetting-list').html('<p class="text-center text-muted">Loading vettings...</p>');

        modal.find('#modal-vetting-bar-good').css('width', '0%').find('span').text('');
        modal.find('#modal-vetting-bar-bad').css('width', '0%').find('span').text('');
        modal.find('#modal-vetting-bar-unknown').css('width', '0%').find('span').text('');

        $.ajax({
            url: '/observations/' + observation_id + '/vettings/',
            dataType: 'json'
        }).done(function (data) {
            console.log('Received data:', data); // Debug

            if (!data || !data.stats || data.stats.total_count === 0) {
                modal.find('#vetting-list').html('<p class="text-center text-muted">No vettings yet</p>');
                modal.find('#vetting-total').text('0');
                return;
            }

            var stats = data.stats;

            // Update summary
            modal.find('#vetting-total').text(stats.total_count);
            modal.find('#vetting-good-count').text(stats.good_count);
            modal.find('#vetting-good-percent').text(stats.good_percentage + '%');
            modal.find('#vetting-bad-count').text(stats.bad_count);
            modal.find('#vetting-bad-percent').text(stats.bad_percentage + '%');
            modal.find('#vetting-unknown-count').text(stats.unknown_count);
            modal.find('#vetting-unknown-percent').text(stats.unknown_percentage + '%');

            if (stats.good_percentage > 0) {
                modal.find('#modal-vetting-bar-good').css('width', stats.good_percentage + '%');
                modal.find('#modal-vetting-bar-good-text').text(stats.good_percentage + '%');
            }

            if (stats.bad_percentage > 0) {
                modal.find('#modal-vetting-bar-bad').css('width', stats.bad_percentage + '%');
                modal.find('#modal-vetting-bar-bad-text').text(stats.bad_percentage + '%');
            }

            if (stats.unknown_percentage > 0) {
                modal.find('#modal-vetting-bar-unknown').css('width', stats.unknown_percentage + '%');
                modal.find('#modal-vetting-bar-unknown-text').text(stats.unknown_percentage + '%');
            }

            // Build vetting list table
            if (!data.vettings || data.vettings.length === 0) {
                modal.find('#vetting-list').html('<p class="text-center text-muted">No individual vettings to display</p>');
                return;
            }

            var vettingHtml = '<table class="table table-sm table-hover">';
            vettingHtml += '<thead><tr><th>User</th><th>Status</th><th>Date</th></tr></thead><tbody>';

            data.vettings.forEach(function(vetting) {
                var badgeClass = '';
                var statusText = '';

                if (vetting.status === 'good') {
                    badgeClass = 'badge-good';
                    statusText = 'With Signal';
                } else if (vetting.status === 'bad') {
                    badgeClass = 'badge-bad';
                    statusText = 'Without Signal';
                } else {
                    badgeClass = 'badge-unknown';
                    statusText = 'Unknown';
                }

                var date = new Date(vetting.datetime);
                var dateStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();

                vettingHtml += '<tr>';
                vettingHtml += '<td><a href="/users/' + vetting.user + '">' + vetting.user + '</a></td>';
                vettingHtml += '<td><span class="badge ' + badgeClass + '">' + statusText + '</span></td>';
                vettingHtml += '<td><small>' + dateStr + '</small></td>';
                vettingHtml += '</tr>';
            });

            vettingHtml += '</tbody></table>';
            modal.find('#vetting-list').html(vettingHtml);

        }).fail(function() {
            modal.find('#vetting-list').html('<p class="text-center text-danger">Failed to load vettings</p>');
        });
    });
}
