/* global WaveSurfer calcPolarPlotSVG */

$(document).ready(observationView);
document.addEventListener('obs_changed', observationView, false);

function observationView() {
    'use strict';

    let obs_vetted = new Event('obs_vetted');

    // Format time for the player
    function formatTime(timeSeconds) {
        var minute = Math.floor(timeSeconds / 60);
        var tmp = Math.round(timeSeconds - (minute * 60));
        var second = (tmp < 10 ? '0' : '') + tmp;
        var seconds_rounded = Math.round(timeSeconds);
        return String(minute + ':' + second + ' / ' + seconds_rounded + ' s');
    }

    // Set width for not selected tabs
    var panelWidth = $('.tab-content').first().width();
    $('.tab-pane').css('width', panelWidth);

    function load_audio_tab() {
        // Waveform loading
        $('.wave').each(function(){
            var $this = $(this);
            var wid = $this.data('id');
            var data_audio_url = $this.data('audio');
            var container_el = '#data-' + wid;
            $(container_el).css('opacity', '0');
            var loading = '#loading-' + wid;
            var $playbackTime = $('#playback-time-' + wid);
            var progressDiv = $('#progress-bar-' + wid);
            var progressBar = $('.progress-bar', progressDiv);

            var showProgress = function (percent) {
                if (percent == 100) {
                    $(loading).text('Analyzing data...');
                }
                progressBar.css('width', percent + '%');
                progressBar.text(percent + '%');
            };

            var hideProgress = function () {
                progressDiv.css('display', 'none');
            };

            var onError = function () {
                hideProgress();
                $('#tab-audio').replaceWith('<div class="notice">Something went wrong, try again later.</div><div class="notice">If the problem persists, please contact an administrator.</div>');
            };

            var wavesurfer = WaveSurfer.create({
                container: container_el,
                waveColor: '#bf7fbf',
                progressColor: 'purple',
                plugins: [
                    WaveSurfer.spectrogram.create({
                        wavesurfer: wavesurfer,
                        container: '#wave-spectrogram',
                        fftSamples: 256,
                        windowFunc: 'hann'
                    })
                ]
            });

            wavesurfer.on('destroy', hideProgress);
            wavesurfer.on('error', onError);

            wavesurfer.on('loading', function(percent) {
                showProgress(percent);
                $(loading).show();
            });

            $this.parents('.observation-data').find('.playpause').click( function(){
                wavesurfer.playPause();
            });

            wavesurfer.load(data_audio_url);

            wavesurfer.on('ready', function() {
                hideProgress();

                //$playbackTime.text(formatTime(wavesurfer.getCurrentTime()));
                $playbackTime.text(formatTime(wavesurfer.getCurrentTime()));

                wavesurfer.on('audioprocess', function(evt) {
                    $playbackTime.text(formatTime(evt));
                });
                wavesurfer.on('seek', function(evt) {
                    $playbackTime.text(formatTime(wavesurfer.getDuration() * evt));
                });
                $(loading).hide();
                $(container_el).css('opacity', '1');
            });
        });
    }

    $('a[href="#tab-audio"]').on('shown.bs.tab', function () {
        load_audio_tab();
        $('a[href="#tab-audio"]').off('shown.bs.tab');
    });

    // Handle Observation tabs
    var uri = new URL(location.href);
    var tab = uri.hash;
    $('.observation-tabs li a[href="' + tab + '"]').tab('show');

    // Delete confirmation
    var message = 'Do you really want to delete this Observation?';
    var actions = $('#obs-delete');
    if (actions.length) {
        actions[0].addEventListener('click', function(e) {
            if (! confirm(message)) {
                e.preventDefault();
            }
        });
    }
    //Vetting help functions
    function show_alert(type, msg){
        $('#alert-messages').html(
            `<div class="col-md-12">
               <div class="alert alert-` + type + ' alert-dismissible" role="alert">'
               + msg +
                `<button type="button" class="close" data-dismiss="alert" aria-label="Close">
                   <span aria-hidden="true">&times;</span>
                 </button>
               </div>
             </div>`);
    }

    function change_vetting_badges(user, datetime, waterfall_status_badge, waterfall_status_display,
        status, status_badge, status_display){
        $('#waterfall-status').find('button').each(function(){
            if(this.dataset.status == waterfall_status_badge){
                $(this).addClass('d-none');
            } else {
                $(this).removeClass('d-none');
            }
        });

        var waterfall_badge_classes = 'badge-unknown badge-with-signal badge-without-signal';
        $('#waterfall-status-badge').removeClass(waterfall_badge_classes).addClass('badge-' + waterfall_status_badge);
        $('#waterfall-status-badge').text(waterfall_status_display);
        var waterfall_status_title = 'Vetted ' + waterfall_status_display + ' on ' + datetime + ' by ' + user;
        if(waterfall_status_badge == 'unknown'){
            waterfall_status_title = 'Waterfall needs vetting';
        }
        $('#waterfall-status-badge').prop('title', waterfall_status_title);

        var rating_badge_classes = 'badge-unknown badge-future badge-good badge-bad badge-failed';
        $('#rating-status span').removeClass(rating_badge_classes).addClass('badge-' + status_badge);
        $('#rating-status span').text(status_display);
        var status_title = status;
        $('#rating-status span').prop('title', status_title);
    }

    function handling_vetting_elements(response){
        if (response){
            $('#vetting-spinner').removeClass('d-inline-block');
            $('#rating-spinner').hide();
            $('#waterfall-status-badge').show();
            $('#waterfall-status-form').show();
            $('#rating-status').show();
        } else {
            $('#waterfall-status-badge').hide();
            $('#waterfall-status-form').hide();
            $('#rating-status').hide();
            $('#vetting-spinner').addClass('d-inline-block');
            $('#rating-spinner').show();
        }
    }

    //Vetting request
    function vet_waterfall(id, vet_status){
        var data = {};
        data.status = vet_status;
        var url = '/waterfall_vet/' + id + '/';
        $.ajax({
            type: 'POST',
            url: url,
            data: data,
            dataType: 'json',
            beforeSend: function(xhr) {
                xhr.setRequestHeader('X-CSRFToken', $('[name="csrfmiddlewaretoken"]').val());
                handling_vetting_elements(false);
            }
        }).done(function(results) {
            if (Object.prototype.hasOwnProperty.call(results, 'error')) {
                var error_msg = results.error;
                show_alert('danger',error_msg);
                handling_vetting_elements(true);
                return;
            }
            show_alert('success', 'Waterfall is vetted succesfully as "' + results.waterfall_status_display + '" and observation status changed to "' + results.status_display + '"');
            change_vetting_badges(results.waterfall_status_user, results.waterfall_status_datetime,
                results.waterfall_status_badge, results.waterfall_status_display,
                results.status, results.status_badge,
                results.status_display);
            handling_vetting_elements(true);
            document.dispatchEvent(obs_vetted);
            return;
        }).fail(function() {
            var error_msg = 'Something went wrong, please try again';
            show_alert('danger', error_msg);
            handling_vetting_elements(true);
            return;
        });
    }

    $('#waterfall-status button').click( function(){
        var vet_status = $(this).data('status');
        var id = $(this).data('id');
        $(this).blur();
        vet_waterfall(id, vet_status);
    });

    //JSON pretty renderer
    var metadata = $('#json-renderer').data('json');
    $('#json-renderer').jsonViewer(metadata, {rootCollapsable: false, withLinks: false});

    // Draw orbit in polar plot
    var tleLine1 = $('svg#polar').data('tle1');
    var tleLine2 = $('svg#polar').data('tle2');

    var timeframe = {
        start: new Date($('svg#polar').data('timeframe-start')),
        end: new Date($('svg#polar').data('timeframe-end'))
    };

    var groundstation = {
        lon: $('svg#polar').data('groundstation-lon'),
        lat: $('svg#polar').data('groundstation-lat'),
        alt: $('svg#polar').data('groundstation-alt')
    };

    const polarPlotSVGPromise = new Promise(function(resolve) {
        resolve(calcPolarPlotSVG(timeframe,
            groundstation,
            tleLine1,
            tleLine2
        ));
    });

    polarPlotSVGPromise.then((polarPlotSVG) => {
        $('svg#polar').append(polarPlotSVG);
    });

    // Return hex string from ArrayBuffer that contains DemodData bytes
    function buffer_to_hex(buffer){
        var hex_string = '';
        var hex_digit = '0123456789ABCDEF';
        (new Uint8Array(buffer)).forEach((v) => {hex_string += hex_digit[v >> 4] + hex_digit[v & 15]+' '; });
        return hex_string.slice(0,-1);
    }

    // Load dynamicaly DemodData files
    function load_demoddata(num){
        $('#load-data-btn-group button').hide();
        $('#demoddata-spinner').show();
        var demoddata_to_show = $('.demoddata:hidden').slice(0, num);
        var number_of_divs = demoddata_to_show.length;
        var divs_shown = 0;
        demoddata_to_show.each(function(){
            var demoddata_div = $(this);
            var content_type = demoddata_div.data('type');
            var url = demoddata_div.find('span:first > a').attr('href');
            if (content_type == 'image'){
                demoddata_div.find('.data-card').append('<img src="' + url + '" alt="DemodData Image" class="img-fluid">');
                demoddata_div.show();
                divs_shown += 1;
                if(divs_shown == number_of_divs){
                    var remaining_data = $('.demoddata:hidden').length;
                    $('#next-data-num').text(Math.min(remaining_data, 10));
                    $('#all-data-num').text(remaining_data);
                    $('#demoddata-spinner').hide();
                    if(remaining_data > 0){
                        $('#load-data-btn-group button').show();
                    }
                }
            } else {
                var xhr = new XMLHttpRequest();
                xhr.open('GET', url, true);
                xhr.responseType = 'arraybuffer';

                xhr.onload = function() {
                    if (this.status == 200) {
                        if (content_type == 'binary'){
                            demoddata_div.find('.data-card').append('<span class="hex">' + buffer_to_hex(this.response) + '</span>');
                            var ascii_enc = new TextDecoder('ascii');
                            demoddata_div.find('.data-card').append('<span class="ascii">' + ascii_enc.decode(this.response) + '</span>');
                            let ax25_html = '';
                            try {
                                const parsedAx25 = new Ax25monitor(new KaitaiStream(this.response)); // eslint-disable-line no-undef
                                const srcCallsign = parsedAx25.ax25Frame.ax25Header.srcCallsignRaw.callsignRor.callsign;
                                const dstCallsign = parsedAx25.ax25Frame.ax25Header.destCallsignRaw.callsignRor.callsign;
                                const alphanum_with_white_spaces_regex = /^[a-z0-9-\s]+$/i;
                                /* eslint-disable quotes*/
                                ax25_html = `
                                  <table class='table table-sm table-borderless table-hover ax25'>
                                    <tbody>
                                      <tr>
                                        <th>
                                          <span class='badge badge-secondary'>Source Callsign</span>
                                        </th>
                                        <td>
                                          <span>` + srcCallsign + `</span>
                                        </td>
                                      </tr>
                                      <tr>
                                        <th>
                                          <span class='badge badge-secondary'>Destination Callsign</span>
                                        </th>
                                        <td>
                                          <span>` + dstCallsign + `</span>
                                        </td>
                                      </tr>
                                      <tr>
                                        <th>
                                          <span class='badge badge-secondary'>Source SSID</span>
                                        </th>
                                        <td>
                                          <span>` + parsedAx25.ax25Frame.ax25Header.srcSsidRaw.ssid + `</span>
                                        </td>
                                      </tr>
                                      <tr>
                                        <th>
                                          <span class='badge badge-secondary'>Destination SSID</span>
                                        </th>
                                        <td>
                                          <span>` + parsedAx25.ax25Frame.ax25Header.destSsidRaw.ssid + `</span>
                                        </td>
                                      </tr>
                                      <tr>
                                        <th>
                                          <span class='badge badge-secondary'>Ctl</span>
                                        </th>
                                        <td>
                                          <span>` + parsedAx25.ax25Frame.ax25Header.ctl + `</span>
                                        </td>
                                      </tr>
                                      <tr>
                                        <th>
                                          <span class='badge badge-secondary'>Pid</span>
                                        </th>
                                        <td>
                                          <span>` + parsedAx25.ax25Frame.payload.pid + `</span>
                                        </td>
                                      </tr>
                                      <tr>
                                        <th>
                                          <span class='badge badge-secondary'>Monitor</span>
                                        </th>
                                        <td>
                                          <span>` + parsedAx25.ax25Frame.payload.ax25Info.dataMonitor + `</span>
                                        </td>
                                      </tr>
                                    </tbody>
                                  </table>`;
                                /* eslint-enable quotes*/
                                if(alphanum_with_white_spaces_regex.test(srcCallsign) === true && alphanum_with_white_spaces_regex.test(dstCallsign) === true) {
                                    $('#ax25-button').show();
                                }
                            }  catch (error) {
                                ax25_html = '<span class="ax25">An error occured during decoding. This might not be an AX.25 packet</span>';
                            }

                            demoddata_div.find('.data-card').append(ax25_html);

                            // check if currently ASCII/HEX/AX25 button is active and display accordingly
                            if ($('#hex-button').hasClass('active')) {
                                demoddata_div.find('.ascii').hide();
                                demoddata_div.find('.ax25').hide();
                            }
                            else if ($('#ascii-button').hasClass('active'))
                            {
                                demoddata_div.find('.hex').hide();
                                demoddata_div.find('.ax25').hide();
                            }
                            else {
                                demoddata_div.find('.hex').hide();
                                demoddata_div.find('.ascii').hide();
                            }

                        } else if (content_type == 'text'){
                            var utf_enc = new TextDecoder('utf-8');
                            demoddata_div.find('.data-card').append('<span class="utf-8">' + utf_enc.decode(this.response) + '</span>');
                        }
                        demoddata_div.show();
                        divs_shown += 1;
                        if(divs_shown == number_of_divs){
                            var remaining_data = $('.demoddata:hidden').length;
                            $('#next-data-num').text(Math.min(remaining_data, 10));
                            $('#all-data-num').text(remaining_data);
                            $('#demoddata-spinner').hide();
                            if(remaining_data > 0){
                                $('#load-data-btn-group button').show();
                            }
                        }
                    }
                };

                xhr.send();
            }
        });
    }

    load_demoddata(10);

    $('#load-next-10-button').click(function(){
        load_demoddata(10);
    });

    $('#load-all-button').click(function(){
        load_demoddata($('.demoddata:hidden').length);
    });

    // Function to convert hex data in each data blob to ASCII, while storing
    // the original blob in a jquery .data, for later reversal back to hex
    // (see next function)
    $('#ascii-button').click(function(){
        $('.hex').hide();
        $('.ax25').hide();
        $('.ascii').show();
        $('#ascii-button').addClass('active');
        $('#hex-button').removeClass('active');
        $('#ax25-button').removeClass('active');
    });

    // retrieve saved hex data and replace the decoded blob with the original
    // hex text
    $('#hex-button').click(function(){
        $('.hex').show();
        $('.ascii').hide();
        $('.ax25').hide();
        $('#hex-button').addClass('active');
        $('#ascii-button').removeClass('active');
        $('#ax25-button').removeClass('active');
    });

    $('#ax25-button').click(function(){
        $('.hex').hide();
        $('.ascii').hide();
        $('.ax25').show();
        $('#ax25-button').addClass('active');
        $('#ascii-button').removeClass('active');
        $('#hex-button').removeClass('active');
    });

    // Hotkeys bindings\
    $(document).unbind('keyup');
    $(document).bind('keyup', function(event){
        if (event.which == 88) {
            var link_delete = $('#obs-delete');
            link_delete[0].click();
        } else if (event.which == 85) {
            var link_unknown = $('#unknown-status');
            link_unknown[0].click();
        } else if (event.which == 71) {
            var link_good = $('#with-signal-status');
            link_good[0].click();
        } else if (event.which == 66) {
            var link_bad = $('#without-signal-status');
            link_bad[0].click();
        }
    });
}
