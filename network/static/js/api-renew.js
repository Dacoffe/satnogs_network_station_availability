$(document).ready(function() {
    'use strict';

    document.getElementById('api-modal-button').addEventListener('click', function(){
        document.getElementById('APIModalTitle').textContent = 'Renew API Key';
        document.getElementById('renew-api-message').hidden = false;
        document.getElementById('api-key').hidden = true;
        document.getElementById('renew-api-form').hidden = false;
        document.getElementById('api-modal-button').hidden = true;
    });

    document.getElementById('api-modal-close-button').addEventListener('click', function(){
        document.getElementById('APIModalTitle').textContent = 'API Key';
        document.getElementById('renew-api-message').hidden = true;
        document.getElementById('api-key').hidden = false;
        document.getElementById('renew-api-form').hidden = true;
        document.getElementById('api-modal-button').hidden = false;
    });
});
