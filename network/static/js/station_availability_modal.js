(function($) {
    'use strict';

    function createModalOverlay() {
        var modalHTML = `
            <div id="availability-modal-overlay" class="modal-overlay" style="display: none;">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-body">
                            <!-- Content will be loaded here -->
                        </div>
                    </div>
                </div>
            </div>
        `;

        if ($('#availability-modal-overlay').length === 0) {
            $('body').append(modalHTML);
        }
    }

    function showAvailabilityModal(modalUrl) {
        createModalOverlay();

        $('#availability-modal-overlay .modal-body').html('<div class="loading">Loading...</div>');
        $('#availability-modal-overlay').fadeIn(300);

        $.get(modalUrl)
            .done(function(data) {
                $('#availability-modal-overlay .modal-body').html(data);

                $('#availability-modal-overlay form').on('submit', function (e) {
                    e.preventDefault();

                    var form = $(this);
                    var formData = form.serialize();

                    $.ajax({
                        type: 'POST',
                        url: modalUrl,
                        data: formData,
                        dataType: 'json',
                        beforeSend: function (xhr) {
                            xhr.setRequestHeader('X-CSRFToken', $('[name="csrfmiddlewaretoken"]').val());
                            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                        },
                        success: function (response) {
                            if (response.success) {
                                $('#availability-modal-overlay').fadeOut(300);

                                if (response.redirect) {
                                    window.location.href = response.redirect;
                                } else {
                                    window.location.reload();
                                }
                            }
                        },
                        error: function (xhr, status, error) {
                            if (xhr.status === 403) {
                                alert('CSRF token error. Please refresh the page and try again.');
                            } else {
                                alert('An error occurred: ' + status + ' - ' + error);
                            }
                        }
                    });
                });

                $('#availability-modal-overlay').on('click', 'button[name="action"]', function (e) {
                    e.preventDefault();

                    var button = $(this);
                    var action = button.val();
                    var form = button.closest('form');

                    button.prop('disabled', true);

                    var formData = form.serialize();
                    formData = formData.replace(/action=[^&]*/, 'action=' + action);
                    if (formData.indexOf('action=') === -1) {
                        formData += '&action=' + action;
                    }

                    $.ajax({
                        type: 'POST',
                        url: modalUrl,
                        data: formData,
                        dataType: 'json',
                        beforeSend: function (xhr) {
                            xhr.setRequestHeader('X-CSRFToken', $('[name="csrfmiddlewaretoken"]').val());
                            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                        },
                        success: function (response) {
                            button.prop('disabled', false);

                            if (response.success) {
                                $('#availability-modal-overlay').fadeOut(300);

                                if (response.redirect) {
                                    window.location.href = response.redirect;
                                } else {
                                    window.location.reload();
                                }
                            }
                        },
                        error: function (xhr, status, error) {
                            button.prop('disabled', false);

                            if (xhr.status === 403) {
                                alert('CSRF token error. Please refresh the page and try again.');
                            } else {
                                alert('An error occurred: ' + status + ' - ' + error);
                            }
                        }
                    });
                });
            })
            .fail(function() {
                $('#availability-modal-overlay .modal-body').html('<p>Error loading modal content.</p>');
            });
    }

    window.showAvailabilityModal = showAvailabilityModal;

    function checkForModal() {
        var currentUrl = window.location.pathname;

        $.get(currentUrl, { check_modal: '1' })
            .done(function(response) {
                if (response.show_modal) {
                    showAvailabilityModal(response.modal_url);
                }
            })
            .fail(function() {
            });
    }

    $(document).ready(function() {
        $('input[name="is_available"]:checkbox').each(function() {
            var checkbox = $(this);
            var initialValue = checkbox.is(':checked');
            checkbox.data('initial-value', initialValue);
        });

        setTimeout(checkForModal, 200);

        if ($('body').data('show-availability-modal')) {
            var modalUrl = $('body').data('modal-url');
            if (modalUrl) {
                showAvailabilityModal(modalUrl);
            }
        }

        $('.submit-row input[name="_save"], .submit-row input[name="_continue"]').on('click', function(e) {
            var saveButton = $(this);
            var form = saveButton.closest('form');
            var isAvailableCheckbox = form.find('input[name="is_available"]:checkbox');

            if (isAvailableCheckbox.length > 0) {
                var currentlyChecked = isAvailableCheckbox.is(':checked');
                var initiallyChecked = isAvailableCheckbox.data('initial-value');

                if (initiallyChecked === true && currentlyChecked === false) {
                    e.preventDefault();
                    e.stopPropagation();

                    saveButton.prop('disabled', true);
                    var formData = form.serialize();
                    if (saveButton.attr('name') && saveButton.val()) {
                        formData += '&' + saveButton.attr('name') + '=' + encodeURIComponent(saveButton.val());
                    }

                    $.ajax({
                        type: 'POST',
                        url: form.attr('action') || window.location.pathname,
                        data: formData,
                        dataType: 'json',
                        beforeSend: function(xhr) {
                            xhr.setRequestHeader('X-CSRFToken', $('[name="csrfmiddlewaretoken"]').val());
                            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                        },
                        success: function() {
                            saveButton.prop('disabled', false);
                            isAvailableCheckbox.data('initial-value', currentlyChecked);

                            setTimeout(function() {
                                checkForModal();
                                setTimeout(function() {
                                    if ($('#availability-modal-overlay').length === 0 || !$('#availability-modal-overlay').is(':visible')) {
                                        saveButton.prop('disabled', false);

                                        var hiddenInput = $('<input type="hidden">');
                                        hiddenInput.attr('name', saveButton.attr('name'));
                                        hiddenInput.attr('value', saveButton.val());
                                        form.append(hiddenInput);

                                        saveButton.off('click');

                                        form.submit();
                                    }
                                }, 500);
                            }, 300);
                        },
                        error: function() {
                            saveButton.prop('disabled', false);

                            var hiddenInput = $('<input type="hidden">');
                            hiddenInput.attr('name', saveButton.attr('name'));
                            hiddenInput.attr('value', saveButton.val());
                            form.append(hiddenInput);

                            saveButton.off('click');
                            form.submit();
                        }
                    });

                    return false;
                }
            }
        });

        $(document).on('submit', '.change-form form', function(e) {
            var form = $(this);
            var isAvailableCheckbox = form.find('input[name="is_available"]:checkbox');

            if (isAvailableCheckbox.length > 0) {
                var currentlyChecked = isAvailableCheckbox.is(':checked');
                var initiallyChecked = isAvailableCheckbox.data('initial-value');

                if (initiallyChecked === true && currentlyChecked === false) {
                    e.preventDefault();

                    $.ajax({
                        type: 'POST',
                        url: form.attr('action') || window.location.pathname,
                        data: form.serialize(),
                        dataType: 'json',
                        beforeSend: function(xhr) {
                            xhr.setRequestHeader('X-CSRFToken', $('[name="csrfmiddlewaretoken"]').val());
                            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                        },
                        success: function() {
                            isAvailableCheckbox.data('initial-value', currentlyChecked);

                            setTimeout(function() {
                                checkForModal();
                                setTimeout(function() {
                                    if ($('#availability-modal-overlay').length === 0 || !$('#availability-modal-overlay').is(':visible')) {
                                        form.off('submit');
                                        form.submit();
                                    }
                                }, 500);
                            }, 300);
                        },
                        error: function() {
                            form.off('submit');
                            form.submit();
                        }
                    });
                }
            }
        });

        $(window).on('load', function() {
            $('input[name="is_available"]:checkbox').each(function() {
                var checkbox = $(this);
                checkbox.data('initial-value', checkbox.is(':checked'));
            });
        });
    });

    // Add support for non-admin forms
    $('#station-edit-form').on('submit', function(e) {
        var form = $(this);
        var isAvailableCheckbox = form.find('input[name="is_available"]:checkbox');

        if (isAvailableCheckbox.length > 0) {
            var currentlyChecked = isAvailableCheckbox.is(':checked');
            var initiallyChecked = isAvailableCheckbox.data('initial-value');

            if (initiallyChecked === true && currentlyChecked === false) {
                e.preventDefault();

                $.ajax({
                    type: 'POST',
                    url: form.attr('action') || window.location.pathname,
                    data: form.serialize() + '&check_availability=1',
                    dataType: 'json',
                    beforeSend: function(xhr) {
                        xhr.setRequestHeader('X-CSRFToken', $('[name="csrfmiddlewaretoken"]').val());
                        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                    },
                    success: function(response) {
                        isAvailableCheckbox.data('initial-value', currentlyChecked);

                        if (response.show_modal && response.modal_url) {
                            showAvailabilityModal(response.modal_url);
                        } else {
                            form.off('submit').submit();
                        }
                    },
                    error: function() {
                        form.off('submit');
                        form.submit();
                    }
                });
            }
        }
    });

})(jQuery);
