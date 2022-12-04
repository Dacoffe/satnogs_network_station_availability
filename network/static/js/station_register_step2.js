/*eslint no-control-regex: 0*/
$(document).ready(function() {
    'use strict';

    var urlParameters = new URLSearchParams(window.location.search);
    var hash = urlParameters.get('hash');

    $('#cancel-register').on('click', function(){
        window.location.href = '/stations/register/step1/?hash=' + hash;
    });

    function check_validity_of_input(element){
        let input = $(element);
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
        let valid = element.checkValidity();
        $('#register').prop('disabled', !$('form')[0].checkValidity());
        input.toggleClass('is-valid', valid);
        input.toggleClass('is-invalid', !valid);
    }

    $('input, textarea').each(function(){
        if(!$(this).hasClass('frequency')){
            check_validity_of_input(this);
        }
    });

    // Events related to validation
    $('body').on('input', function(e){
        check_validity_of_input(e.target);
    });
});
