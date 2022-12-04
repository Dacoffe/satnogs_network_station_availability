$(document).ready(function() {
    'use strict';

    var urlParameters = new URLSearchParams(window.location.search);
    var hash = urlParameters.get('hash');

    $('button').on('click', function(){
        if(this.id == 'new-station'){
            window.location.href = '/stations/register/step2/?hash=' + hash;
        } else {
            var station = this.dataset.station;
            window.location.href = '/stations/register/step2/' + station + '/?hash=' + hash;
        }
    });
});
