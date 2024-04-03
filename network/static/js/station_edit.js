/*global human_frequency, bands_from_range, JSONEditor*/
/*eslint no-control-regex: 0*/
$(document).ready(function() {
    'use strict';

    let jsonEditor = null;
    let stationType = -1;
    let schemaId = -1;
    let schema = null;
    const isStationRegistered = document.getElementById('configuration-card-body').dataset['registered'] === 'True';
    const hasUnregisteredConfiguration = document.getElementById('configuration-card-body').dataset['hasUnregisteredConfiguration'] === 'True';
    const currentConfigurationScript = document.getElementById('current-configuration');
    let configuration;
    let earlierConfiguration = null;

    if(currentConfigurationScript) {
        configuration = JSON.parse(document.getElementById('current-configuration').textContent);
        if(isStationRegistered && hasUnregisteredConfiguration) {
            earlierConfiguration = configuration;
            configuration = null;
        }
    } else {
        configuration = null;
    }

    const allSchemas = $('#configuration-schema-selection option').clone().toArray();

    /* States the station can be in:
     * 1) Unregistered with default unregistered configuration.
     * 2) Registered with default unregistered configuration (occurs when in the process of registering an existing unregistered station)
     * 3) Registered with no configuration (occurs while following the registration process for a new station)
     * 4) Registered with configuration other than the default unregistered configuration
     */

    if(!isStationRegistered) {    // Case #1
        // If there is only one station type, it will be selected by default in the template.
        // Also, by being unregistered, the unregistered schema will also be selected.
        schemaId = $('#configuration-schema-selection').val();
        $('#configuration-schema-selection-container').removeClass('is-invalid');
        $('#config-required-asterisk').removeClass('station-type-invalid');
        $('#config-required-asterisk').removeClass('schema-invalid');
        selectSchemaById(schemaId);
    } else if(!configuration && !(isStationRegistered && hasUnregisteredConfiguration)) {   // Case #3
        $('#configuration-schema-selection-container').hide();
    } else {    // Cases #2 and #4
        schemaId = $('#configuration-schema-selection').val();
        if(schemaId !== '-1') {     // Case #2 because the unregistered configuration is removed from the <select>
            selectSchemaById(schemaId);
        } else {    // Case #4
            $('#configuration-schema-selection-container').addClass('is-invalid');
            $('#config-required-asterisk').addClass('station-type-invalid');
        }
    }

    function setSchemaOptionsForStationTypeID(stationTypeId) {
        $('#configuration-schema-selection').empty();
        const schemaOptions = allSchemas.filter(element => {
            return (element.dataset['stationType'] === stationTypeId || element.value === '-1');
        });
        $('#configuration-schema-selection').append(schemaOptions);
    }

    function selectSchemaById(currentSchemaId) {
        schema = JSON.parse(document.getElementById(currentSchemaId).textContent);
        if(jsonEditor) {
            jsonEditor.destroy();
        }
        jsonEditor = new JSONEditor(document.getElementById('json-editor-container'), {
            theme: 'bootstrap4',
            schema: schema,
            // If it's a registered station but hasn't changed the unregistered configuration, 
            // keep the common settings as startval when moving to another schema
            startval: earlierConfiguration || configuration,
            show_errors: 'interaction',
            iconlib: 'bootstrap',
            remove_button_labels: true,
            disable_properties: true,
            disable_edit_json: true,
            display_required_only: true
        });
        jsonEditor.on('ready',() => {
            $('#advancedEditInput').val(JSON.stringify(jsonEditor.getValue(), null, 2));
            configuration = jsonEditor.getValue();

            // Hack to trigger validation on each keystroke
            $('#json-editor-container').find('input').on('input', function() {
                var event = new Event('change', {
                    'bubbles': true,
                    'cancelable': true
                });
                this.dispatchEvent(event);
            });

            $('#json-renderer').jsonViewer(configuration, {rootCollapsable: false, withLinks: false});
            $('#submit').prop('disabled', !$('form')[0].checkValidity() || !configuration);
        });
        
        jsonEditor.on('change',function() {
            const errors = jsonEditor.validate();
            if(errors.length) {
                $('#modal-save-config').prop('disabled', true);
            } else {
                $('#modal-save-config').prop('disabled', false);
            }
        });
        $('#conf-controls-container').show();
        $('#submit').prop('disabled', !$('form')[0].checkValidity());
    }

    $('#station-type-selection').on('changed.bs.select', function(event) {
        stationType = event.target.value;
        if(stationType == -1) {
            $('#station-type-selection-container').addClass('is-invalid'); // Add this to parent formgroup to display red border
            $('#config-required-asterisk').addClass('station-type-invalid'); // Add this to display the red asterisk meaning 'required'
            $('#configuration-schema-selection-container').hide();
            configuration = null;
            $('#submit').prop('disabled', true);
            $('#conf-controls-container').hide();
        } else {
            $('#station-type-selection-container').removeClass('is-invalid');
            $('#config-required-asterisk').removeClass('station-type-invalid');
            setSchemaOptionsForStationTypeID(stationType);
            $('#configuration-schema-selection').selectpicker('refresh');
            $('#configuration-schema-selection-container').show();
            // If station is unregistered the unregistered configuration
            // for the station type is selected already
            schemaId = $('#configuration-schema-selection').val();
            if(schemaId !== '-1') {
                selectSchemaById(schemaId);
                $('#configuration-schema-selection-container').removeClass('is-invalid');
                $('#config-required-asterisk').removeClass('schema-invalid');
            } else {
                $('#configuration-schema-selection-container').addClass('is-invalid');
                $('#config-required-asterisk').addClass('schema-invalid');
            }
        }
    });

    $('#configuration-schema-selection').on('changed.bs.select', function(event) {
        schemaId = event.target.value;
        if(schemaId == -1) {
            $('#configuration-schema-selection-container').addClass('is-invalid');
            $('#config-required-asterisk').addClass('schema-invalid');
            $('#conf-controls-container').hide();
            jsonEditor.destroy();
            jsonEditor = null;
            configuration = null;
            $('#submit').prop('disabled', true);
        } 
        else {
            $('#configuration-schema-selection-container').removeClass('is-invalid');
            $('#config-required-asterisk').removeClass('schema-invalid');
            selectSchemaById(schemaId);
        }
    });


    $('#edit-conf').on('click', function() {
        $('#advanced-edit-conf-modal').modal('hide');
        $('#edit-conf-modal').modal('show');
    });

    $('#modal-save-config').on('click', function() {
        const nonValidatedConfiguration = jsonEditor.getValue();
        const errors = jsonEditor.validate(nonValidatedConfiguration);
        if(!errors.length) {
            configuration = nonValidatedConfiguration;
            $('#advancedEditInput').val(JSON.stringify(jsonEditor.getValue(), null, 2));
            $('#json-renderer').jsonViewer(configuration, {rootCollapsable: false, withLinks: false});
            $('#edit-conf-modal').modal('hide');
        }
    });
    
    // Discards non-saved edits when closing the edit modal
    $('#edit-conf-modal').on('hide.bs.modal', function() {
        selectSchemaById(schemaId);
    });

    function validateAdvancedEdit(textareaValue) {
        let advancedEditConf;
        let errors;
        try {
            advancedEditConf = JSON.parse(textareaValue);
            errors = jsonEditor.validate(advancedEditConf);
        } catch (error) {
            errors = [{'path': 'JSON error', 'message': 'Could not parse JSON'}];
        }
        if(errors.length) {
            const errorContainer = document.getElementById('advanced-edit-errors');
            errorContainer.innerHTML = '';
            errors.forEach(function(error) {
                errorContainer.innerText += `${error.path}: ${error.message}`;
            });
            $('#advanced-edit-errors').show();
            $('#save-advanced-edit').prop('disabled', true);
            $('#advancedEditInput').addClass('is-invalid').removeClass('is-valid');
            // format: [isValid, parsedJSONConfig]
            return [false, null];
        } else {
            $('#advanced-edit-errors').hide();
            $('#save-advanced-edit').prop('disabled', false);
            $('#advancedEditInput').addClass('is-valid').removeClass('is-invalid');
            // format: [isValid, parsedJSONConfig]
            return [true, advancedEditConf];
        }
    }

    $('#advancedEditInput').on('input', function(event) {
        validateAdvancedEdit(event.target.value);
    });

    $('#advanced-edit-conf').on('click', function() {
        $('#edit-conf-modal').modal('hide');
        $('#advanced-edit-conf-modal').modal('show');
    });

    $('#advanced-edit-conf-modal').on('hide.bs.modal', function() {
        $('#advancedEditInput').val(JSON.stringify(jsonEditor.getValue(), null, 2));
    });

    $('#save-advanced-edit').on('click', function() {
        const [isValid, advancedEditConf] =  validateAdvancedEdit($('#advancedEditInput').val());
        if(isValid) {
            jsonEditor.setValue(advancedEditConf);
            configuration = advancedEditConf;
            $('#json-renderer').jsonViewer(configuration, {rootCollapsable: false, withLinks: false});
            $('#advanced-edit-conf-modal').modal('hide');
        }
    });

    $('#antennas-loading').toggle();
    $('.selectpicker').selectpicker();

    $('.card-body.collapse').on('hide.bs.collapse', function () {
        $(this).parent().find('.card-header i').addClass('bi-arrows-collapse').removeClass('bi-arrows-expand');
    });

    $('.card-body.collapse').on('show.bs.collapse', function () {
        $(this).parent().find('.card-header i').addClass('bi-arrows-expand').removeClass('bi-arrows-collapse');
    });

    // Parse and initialize station data and remove html elements that holding them
    var station_element = $('#station-data-to-parse');
    var station_data = station_element.data();
    const max_frequency_ranges = station_data.max_frequency_ranges_per_antenna;
    const max_antennas = station_data.max_antennas_per_station;
    const maximum_frequency = station_data.max_frequency_for_range;
    const minimum_frequency = station_data.min_frequency_for_range;
    const vhf_max = station_data.vhf_max_frequency;
    const vhf_min = station_data.vhf_min_frequency;
    const uhf_max = station_data.uhf_max_frequency;
    const uhf_min = station_data.uhf_min_frequency;
    const s_max = station_data.s_max_frequency;
    const s_min = station_data.s_min_frequency;
    const l_max = station_data.l_max_frequency;
    const l_min = station_data.l_min_frequency;
    station_element.remove();

    // Parse and initialize antenna data and remove html elements that holidng them
    var current_antenna = {};
    var current_order = -1;
    var antenna_element = $('#antennas-data-to-parse');
    var antennas = [];

    function get_band_range(frequency_data){
        let range = {
            'min': frequency_data.min,
            'human_min': human_frequency(frequency_data.min),
            'max': frequency_data.max,
            'human_max': human_frequency(frequency_data.max),
            'bands': bands_from_range(frequency_data.min, frequency_data.max),
            'initial': Object.prototype.hasOwnProperty.call(frequency_data, 'id'),
            'deleted': Object.prototype.hasOwnProperty.call(frequency_data, 'deleted')
        };
        if(range.initial){
            range.id = frequency_data.id;
        }
        return range;
    }

    antenna_element.children().each(function(){
        var antenna_data = $(this).data();
        var frequency_ranges = [];
        $(this).children().each(function(){
            var frequency_data = $(this).data();
            frequency_ranges.push(
                get_band_range(frequency_data)
            );
        });
        let antenna = {
            'type_name': antenna_data.typeName,
            'type_id': antenna_data.typeId,
            'initial': Object.prototype.hasOwnProperty.call(antenna_data, 'id'),
            'deleted': Object.prototype.hasOwnProperty.call(antenna_data, 'deleted'),
            'frequency_ranges': frequency_ranges
        };
        if(antenna.initial){
            antenna.id = antenna_data.id;
        }
        antennas.push(antenna);
    });
    antenna_element.remove();

    // Functions to create and update antenna cards
    function create_antenna_card(antenna, order){
        var frequency_ranges_elements ='';
        for(let range of antenna.frequency_ranges){
            if(!range.deleted){
                frequency_ranges_elements += '<div>'+ range.human_min + ' - ' + range.human_max + ' (' + range.bands + ')</div>';
            }
        }
        var add_frequency_ranges_button = '<button type="button" data-action="edit" data-order="' + order + `" class="btn btn-sm btn-primary" data-toggle="modal" data-target="#modal">
                                             <span class="bi bi-plus" aria-hidden="true"></span>
                                             Add frequency ranges
                                           </button>`;
        frequency_ranges_elements = frequency_ranges_elements || add_frequency_ranges_button;
        return '<div class="card m-2" id="' + order + `">
                  <div class="card-header">
                    <div class="row justify-content-between align-items-center">
                      <div class="col-">
                        <div class="antenna-label">` + antenna.type_name + `</div>
                      </div>
                      <div class="col-">
                        <button type="button" data-action="edit" data-order="` + order + `" data-toggle="modal" data-target="#modal" class="btn btn-sm btn-primary float-right">
                          <span class="bi bi-pencil-square" aria-hidden="true"></span>
                          Edit
                        </button>
                      </div>
                    </div>
                  </div>
                  <div class="card-body text-center">
                    <div class="antenna-label">Frequency Ranges:</div>
                    <div class="frequency-ranges">
                      ` + frequency_ranges_elements + `
                    </div>
                  </div>
                </div>`;
    }

    function update_antennas_cards(){
        $('#antennas-loading').show();
        $('#antennas-card-body').addClass('d-none');
        $('#antennas-card-group .card').remove();
        let antennas_cards = '';
        let deleted = 0;
        antennas.forEach(function(antenna, order){
            if(!antenna.deleted){
                antennas_cards += create_antenna_card(antenna, order);
            } else {
                deleted++;
            }
        });
        $('#new-antenna').toggle(
            (antennas.length - deleted) < max_antennas
        );
        $('#antennas-card-group').prepend(antennas_cards);
        $('#antennas-loading').hide();
        $('#antennas-card-body').removeClass('d-none');
    }

    // Create initial antenna bootstrap cards if antennas exist
    update_antennas_cards();

    // Form fields validations
    function update_text_input_and_validation(text_input, text, valid){
        text_input.val(text);
        text_input.toggleClass('is-valid', valid);
        text_input.toggleClass('is-invalid', !valid);

    }

    function check_validity_of_frequencies(){
        $('button[data-action=save]').prop('disabled', false);
        let valid = true;

        for(let order in current_antenna.frequency_ranges){
            let valid_range = true;
            let range = current_antenna.frequency_ranges[order];

            if(range.deleted){
                continue;
            }

            let min = parseInt(range.min);
            let max = parseInt(range.max);
            let text_input = $('#' + order + '-range-text');

            if(isNaN(min) || isNaN(max)){
                valid_range = false;
                update_text_input_and_validation(text_input, 'Invalid minimum or maximum value', false);
                continue;
            } else if(max < min){
                valid_range = false;
                update_text_input_and_validation(text_input, 'Minimum value is greater than maximum value', false);
                continue;
            } else if(min < minimum_frequency || max > maximum_frequency){
                valid_range = false;
                update_text_input_and_validation(text_input, 'Minimum or maximum value is out of range', false);
                continue;
            }

            for(let index in current_antenna.frequency_ranges){
                let index_range = current_antenna.frequency_ranges[index];
                let index_min = parseInt(index_range.min);
                let index_max = parseInt(index_range.max);
                if(index_range.deleted || index === order || isNaN(index_min) || isNaN(index_max)){
                    continue;
                }
                if(index_min < min && index_max > max) {
                    valid_range = false;
                    update_text_input_and_validation(text_input, 'Range is subset of another range', false);
                    break;
                } else if(index_min > min && index_max < max) {
                    valid_range = false;
                    update_text_input_and_validation(text_input, 'Range is superset of another range', false);
                    break;
                } else if(!(index_min > max || index_max < min)){
                    valid_range = false;
                    update_text_input_and_validation(text_input, 'Range conflicts with another range', false);
                    break;
                }
            }

            if(valid_range){
                range.human_min = human_frequency(range.min);
                range.human_max = human_frequency(range.max);
                range.bands = bands_from_range(range.min, range.max);
                update_text_input_and_validation(text_input, range.human_min + '-' + range.human_max + '(' + range.bands + ')', true);
            } else {
                valid = false;
            }
        }

        if(!valid) {
            $('button[data-action=save]').prop('disabled', true);
        }
    }

    function check_validity_of_input(element){
        let input = $(element);
        if(element.id === 'station-name' || element.id === 'description'){
            /* Limit letters of description and name to ISO/IEC 8859-1 (latin1)
               https://en.wikipedia.org/wiki/ISO/IEC_8859-1 */
            let constraint = new RegExp('[^\n\r\t\x20-\x7E\xA0-\xFF]', 'gi');
            if(element.id === 'station-name'){
                constraint = new RegExp('[^\x20-\x7E\xA0-\xFF]', 'gi');
            }
            if(constraint.test(input.val())){
                element.setCustomValidity('Please use characters that belong to ISO-8859-1 (https://en.wikipedia.org/wiki/ISO/IEC_8859-1)');
            } else {
                element.setCustomValidity('');
            }
        }
        let valid = element.checkValidity();
        // Toggle the 'required' red asterisc in General Info based on 'name' input validity
        if(element.id === 'station-name') {
            if(valid) {
                $('#general-info-required').addClass('d-none');
            } else {
                $('#general-info-required').removeClass('d-none');
            }
        }
        $('#submit').prop('disabled', !$('form')[0].checkValidity() || !configuration);
        input.toggleClass('is-valid', valid);
        input.toggleClass('is-invalid', !valid);
    }

    $('input, textarea').not($('#json-editor-container input, #json-editor-container textarea')).each(function(){
        if(!$(this).hasClass('frequency')){
            check_validity_of_input(this);
        }
    });

    // Events related to validation
    $('body').on('input', function(e){
        // Exlude the inputs if jsonEditor
        if ($(e.target).closest('#json-editor-container').length || $(e.target).attr('id') === 'advancedEditInput') {
            return;
        }
        let input = $(e.target);
        let value = input.val();
        let order = input.data('order');
        let field = input.data('field');
        if(input.hasClass('frequency')){
            current_antenna.frequency_ranges[order][field] = value;
            check_validity_of_frequencies();
        } else {
            check_validity_of_input(e.target);
        }
    });

    // Functions to initialize modal
    function band_ranges(band){
        switch(band){
        case 'VHF':
            return get_band_range({'min': vhf_min, 'max': vhf_max});
        case 'UHF':
            return get_band_range({'min': uhf_min, 'max': uhf_max});
        case 'L':
            return get_band_range({'min': l_min, 'max': l_max});
        case 'S':
            return get_band_range({'min': s_min, 'max': s_max});
        default:
            return get_band_range({'min': minimum_frequency, 'max': maximum_frequency});
        }
    }

    function create_frequency_range_card(range, order){
        return `<div class="card my-2 p-2 bg-light border border-secondary">
                  <div class="form-group">
                    <div data-order="` + order + `" class='row no-gutters justify-content-between align-items-center frequency-range-fields'>
                      <div class='col'>
                        <div class='row'>
                          <div class='col'>
                            <label for="` + order + `-min" class="control-label">Minimum</label>
                            <input data-order="` + order + '" data-field="min" value="' + range.min + '" id="' + order + '-min" type="number" min="' + minimum_frequency + '" max="' + maximum_frequency + `" class="form-control frequency" placeholder="Minimum Frequency">
                          </div>
                          <div class='col'>
                            <label for="` + order + `-max" class="control-label">Maximum</label>
                            <input data-order="` + order + '" data-field="max" value="' + range.max + '" id="' + order + '-max" type="number" min="' + minimum_frequency + '" max="' + maximum_frequency + `" class="form-control frequency " placeholder="Maximum Frequency">
                          </div>
                        </div>
                        <div class='row'>
                          <div class='col'>
                            <input id="` + order + '-range-text" readonly="" type="text" value="' + range.human_min + ' - ' + range.human_max + ' (' + range.bands + `)" class="form-control text-center">
                          </div>
                        </div>
                      </div>
                      <div class='col- text-center'>
                        <button class="btn btn-danger m-4 remove-range" type="button" data-order="` + order + `" aria-label="Remove frequency range">
                          <span class="bi bi-x"></span>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>`;
    }

    function update_frequency_ranges_cards(){
        $('#frequency-ranges-loading').show();
        $('#frequency-ranges').hide();
        $('#frequency-ranges .card').remove();
        let frequency_ranges_cards = '';
        let deleted = 0;
        current_antenna.frequency_ranges.forEach(function(frequency_range, order){
            if(!frequency_range.deleted){
                frequency_ranges_cards += create_frequency_range_card(frequency_range, order);
            } else {
                deleted++;
            }
        });
        $('#new-ranges').toggle(
            (current_antenna.frequency_ranges.length - deleted) < max_frequency_ranges
        );
        if((current_antenna.frequency_ranges.length - deleted) == 0){
            frequency_ranges_cards = 'Add a frequency range by choosing one of the default ranges or a custom one bellow<hr>';
        }
        $('#frequency-ranges').html(frequency_ranges_cards);
        check_validity_of_frequencies();
        $('#frequency-ranges-loading').hide();
        $('#frequency-ranges').show();
    }

    // Events related to modal
    $('#antenna-type').on('changed.bs.select', function (e, clickedIndex, isSelected) {
        if(isSelected !== null){
            let value = e.target.value;
            current_antenna.type_name = $('option[value=' + value + ']').data('content');
            current_antenna.type_id = value;
        }
    });

    $('#frequency-ranges').on('click', '.remove-range',function(e){
        let order = $(e.currentTarget).data('order');
        if(current_antenna.frequency_ranges[order].initial){
            current_antenna.frequency_ranges[order].deleted = true;
        } else {
            current_antenna.frequency_ranges.splice(order, 1);
        }
        update_frequency_ranges_cards();
    });

    $('.new-range').on('click', function(){
        let range = band_ranges($(this).data('range'));
        current_antenna.frequency_ranges.push(range);
        update_frequency_ranges_cards();
    });

    $('#modal').on('show.bs.modal', function (e) {
        $('#submit').prop('disabled', true); // Disable submit button
        let action = $(e.relatedTarget).data('action');
        if(action == 'edit'){
            let order = $(e.relatedTarget).data('order');
            $('#AntennaModalTitle').text('Edit Antenna');
            current_antenna = $.extend(true, {}, antennas[order]);
            current_order = order;
            $('#antenna-type').selectpicker('val', antennas[order].type_id);
            $('#delete-antenna').show();

        } else if(action == 'new'){
            $('#AntennaModalTitle').text('New Antenna');
            let value = $('#antenna-type').children(':first').val();
            current_antenna = {'type_name': $('option[value=' + value + ']').data('content'), 'type_id': value, 'initial': false, 'deleted': false, 'frequency_ranges': []};
            current_order = -1;
            $('#antenna-type').selectpicker('val', value);
            $('#delete-antenna').hide();
        }
        update_frequency_ranges_cards();
    });

    $('#modal').on('click', '.modal-action', function (e) {
        let action = $(e.currentTarget).data('action');
        let order = current_order;
        if(action == 'save'){
            let to_save_antenna = $.extend(true, {}, current_antenna);
            to_save_antenna.frequency_ranges.forEach(function(range){
                range.human_min = human_frequency(range.min);
                range.human_max = human_frequency(range.max);
                range.bands = bands_from_range(range.min, range.max);
            });
            if(current_order >= 0){
                antennas[order] = to_save_antenna;
            } else {
                antennas.push(to_save_antenna);
            }
        } else if(action == 'delete'){
            if(antennas[order].initial){
                antennas[order].deleted = true;
            } else {
                antennas.splice(order, 1);
            }
        }
        update_antennas_cards();
        $(e.delegateTarget).modal('hide');
    });

    $('#modal').on('hidden.bs.modal', function () {
        let value = $('#antenna-type').first().val();
        current_antenna = {'type_name': $('option[value=' + value + ']').data('content'), 'type_id': value, 'initial': false, 'deleted': false, 'frequency_ranges': []};
        $('#antenna-type').selectpicker('val', value);
        $('#frequency-ranges').html('Add a frequency range by choosing one of the default ranges or a custom one bellow<hr>');
        $('#frequency-ranges').show();
        $('#delete-antenna').hide();
        $('#submit').prop('disabled', false); // Enable submit button
    });

    // Initialize Station form elements
    var horizon_value = $('#horizon').val();
    $('#horizon').slider({
        id: 'horizon_value',
        min: 0,
        max: 90,
        step: 1,
        value: horizon_value});

    var utilization_value = $('#utilization').val();
    $('#utilization').slider({
        id: 'utilization_value',
        min: 0,
        max: 100,
        step: 1,
        value: utilization_value});

    var image_exists = Object.prototype.hasOwnProperty.call($('#station-image').data(), 'existing');
    var send_remove_file = false;
    if(image_exists){
        $('#station-image').fileinput({
            showRemove: true,
            showUpload: false,
            showClose: false,
            initialPreview: $('#station-image').data('existing'),
            initialPreviewAsData: true,
            initialPreviewShowDelete: false,
            allowedFileTypes: ['image'],
            autoOrientImage: false,
            fileActionSettings: {
                showDownload: false,
                showRemove: false,
                showZoom: true,
                showDrag: false,
            }
        });
    } else {
        $('#station-image').fileinput({
            showRemove: true,
            showUpload: false,
            showClose: false,
            allowedFileTypes: ['image'],
            autoOrientImage: false,
            fileActionSettings: {
                showDownload: false,
                showRemove: false,
                showZoom: true,
                showDrag: false,
            }
        });
    }

    $('#satnogs-rx-samp-rate').on('change', function(){
        if (this.value) {
            this.value = Number(this.value);
        }
    });

    $('#station-image').on('change', function() {
        send_remove_file = false;
    });

    $('#station-image').on('fileclear', function() {
        send_remove_file = image_exists;
    });

    $('#violator_scheduling').change(function(){
        $('.violator-scheduling-option-description').hide();
        $('#violator-scheduling-'+ this.value).show();
    });
    $('#violator_scheduling').change();

    // Submit or Cancel form
    $('#cancel').on('click', function(){
        if(this.textContent == 'Back to Dashboard'){
            location.href = location.origin + '/users/redirect/';
        } else {
            location.href = location.href.replace('edit/','');
        }
    });

    $('form').on('submit', function(){
        $('#antenna-type').remove();
        let antennas_total = 0;
        let antennas_initial = 0;
        let form = $('form');
        // Prepare station form
        if(send_remove_file){
            form.append('<input type="checkbox" name="image-clear" style="display: none" checked>');
        }
        // Prepare antennas forms
        antennas.forEach(function(antenna, order){
            antennas_total++;
            let antenna_prefix = 'ant-' + order;
            if(antenna.deleted){
                form.append('<input type="checkbox" name="' + antenna_prefix + '-DELETE" style="display: none" checked>');
            }
            if(antenna.initial){
                antennas_initial++;
                form.append('<input type="hidden" name="' + antenna_prefix + '-id" value="' + antenna.id + '">');
            }
            form.append('<input type="hidden" name="' + antenna_prefix + '-antenna_type" value="' + antenna.type_id + '">');

            //Prepare frequency ranges forms
            let frequency_ranges_total = 0;
            let frequency_ranges_initial = 0;
            antenna.frequency_ranges.forEach(function(range, range_order){
                frequency_ranges_total++;
                let range_prefix = antenna_prefix + '-fr-' + range_order;
                if(range.deleted){
                    form.append('<input type="checkbox" name="' + range_prefix + '-DELETE" style="display: none" checked>');
                }
                if(range.initial){
                    frequency_ranges_initial++;
                    form.append('<input type="hidden" name="' + range_prefix + '-id" value="' + range.id + '">');
                }
                form.append('<input type="hidden" name="' + range_prefix + '-min_frequency" value="' + range.min + '">');
                form.append('<input type="hidden" name="' + range_prefix + '-max_frequency" value="' + range.max + '">');
            });
            form.append('<input type="hidden" name="' + antenna_prefix + '-fr-TOTAL_FORMS" value="' + frequency_ranges_total + '">');
            form.append('<input type="hidden" name="' + antenna_prefix + '-fr-INITIAL_FORMS" value="' + frequency_ranges_initial + '">');
            form.append('<input type="hidden" name="' + antenna_prefix + '-fr-MAX_NUM_FORMS" value="' + max_frequency_ranges + '">');
        });

        form.append('<input type="hidden" name="ant-TOTAL_FORMS" value="' + antennas_total + '">');
        form.append('<input type="hidden" name="ant-INITIAL_FORMS" value="' + antennas_initial + '">');
        form.append('<input type="hidden" name="ant-MAX_NUM_FORMS" value="' + max_antennas + '">');

        form.append('<input type="hidden" name="lat" value="' + (configuration['Location Configuration'] ? configuration['Location Configuration']['station_lat']: 0) + '">');
        form.append('<input type="hidden" name="lng" value="' + (configuration['Location Configuration'] ? configuration['Location Configuration']['station_lon']: 0) + '">');
        form.append('<input type="hidden" name="alt" value="' + (configuration['Location Configuration'] ? configuration['Location Configuration']['station_elev']: 0) + '">');
        form.append('<input type="hidden" name="schema" value="' + schemaId + '">');
        form.append('<input id="station-configuration-form-input" type="hidden" name="station_configuration" value="">');
        $('#station-configuration-form-input').val(JSON.stringify(configuration));
    });
});