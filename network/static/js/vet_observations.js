/* The view that loads this script (VetObservationsView) displays the first object
    in the queryset. This script fetches the pages of the paginated queryset and cycles 
    through the observations using btn_prev and btn_next.
*/

document.addEventListener('DOMContentLoaded', () => {
    let container = document.getElementById('vet-obs-container');
    const query_url = container.dataset['query_url'];  // The url to send the AJAX request to get the chunks

    const obs_ids = JSON.parse(document.getElementById('obs-ids').textContent);
    const total_items = obs_ids.length;
    const page_size = parseInt(container.dataset.page_size);
    const total_pages_num = Math.ceil(total_items / page_size);
    const fwd_buffer_chunks = parseInt(container.dataset['fwd_buffer_chunks']);  // The number of next pages to hold in memory
    const bwd_buffer_chunks = parseInt(container.dataset['bwd_buffer_chunks']);  // The number of previous pages to hold in memory
    const chunks_buffer_headstart = Math.min(parseInt(container.dataset['chunks_buffer_headstart']), total_pages_num - 1);  // The number of pages to load besides the first, at the start of the vetting proccess

    let btn_prev = document.getElementById('btn-prev');
    let btn_next = document.getElementById('btn-next');
    let loading_spinner = document.getElementById('obs-loading');  // The spinner that displays instead of the 'next' button when next pages have not loaded yet
    let pages = {};  // Holds the arrays of observations' html(pages), using the page number (starting from 1) as key 
    let current_page_num = 1;
    let current_obs_index = 0;  // The index of the observation in each page (0 to page_size-1) 
    const current_obs_display = document.getElementById('current-obs-display');  // The number of the displayed observation
    let obs_changed_event = new Event('obs_changed');  // Causes observation_view.js to add listeners for each observation
    let auto_advance_checkbox = document.getElementById('auto-advance-checkbox');
    let waterfalls = {};
    let wavesurfer = null;  // Reference to wavesurfer. It is set when the audio tab is loaded via custom event
    
    btn_prev.disabled = true;
    btn_next.disabled = true;
    auto_advance_checkbox.checked = true;

    if(total_items) {
        document.getElementById('total-obs-display').innerHTML = total_items;
    }

    window.addEventListener('wavesurferCreated', function(event) {
        // Saves the reference to wavesurfer when the audio tab is loaded
        wavesurfer = event.detail;
    });

    function preload_waterfall(obs_html_list, page_num) {
    /* Search through the html of each observation and download the waterfall images.
        No need to store them in javascript as they are cached by the browser.
    */
        function extract_img_url(html_string) {
            const regex = /<img[^>]+id="waterfall-img"[^>]+data-src="(.*?)"/g;
            let match;
        
            if ((match = regex.exec(html_string)) !== null) {
                return match[1];
            }
            return null;
        }
        
        obs_html_list.forEach((obs_html, idx) => {
            let src = extract_img_url(obs_html);
            if (src) {
                fetch(src).then(response => response.blob())
                    .then(blob => waterfalls[`${page_num.toString()}-${idx.toString()}`] = blob);
            }
        });
    } 

    function set_copy_link_btn() {
    // Copies the link to the observation's detail page to the clipboard.
        if(total_items) {
            let copy_link_btn = document.getElementById('copy-link-btn');
            let full_uri = `${window.location.protocol}//${window.location.host}${copy_link_btn.dataset['permalink']}`;
            copy_link_btn.addEventListener('click', () => {
                navigator.clipboard.writeText(full_uri)
                    .then(() => {
                        copy_link_btn.innerHTML = 'Copied!';
                    });
            });
        }
    }

    function update_obs_num_display() {
        // Updates the observation number in the HTML
        current_obs_display.innerHTML = (current_obs_index + 1) + (current_page_num - 1) * page_size;
    }

    function get_page_num_to_clean_bwd(current_page_num) {
        // Returns the page number to be removed from memory when moving to next pages
        if(current_page_num - 1 > bwd_buffer_chunks) {
            return current_page_num - bwd_buffer_chunks - 1;
        }
        return null;
    }

    function get_page_num_to_clean_fwd(current_page_num) {
        // Returns the page number to be removed from memory when moving to previous pages
        if(current_page_num + fwd_buffer_chunks + 1 <= total_pages_num) {
            return current_page_num + bwd_buffer_chunks + 1;
        }
        return null;
    }

    function delete_page(delete_page_num) {
        // Deletes the chunk and associated waterfalls from memory
        pages[delete_page_num] = null;
        for(let i=0;i<page_size;i++) {
            waterfalls[`${delete_page_num.toString()}-${i.toString()}`] = null;
        }
    }

    function hide_alert(){
        $('#alert-messages').html('');
    }

    function save_current_obs_state() {
        if(wavesurfer) {    // If audio is playing, stop it
            wavesurfer.stop();
            wavesurfer.destroy();
        }
        // Saves changes made to the DOM to the in-memory HTML
        pages[current_page_num.toString()][current_obs_index] = container.innerHTML;
    }

    function waitForSatelliteModalClose() {
        // Waits util the Satellite modal is closed
        const satModal = $('#SatelliteModal');
        if (satModal.hasClass('show')) {
            satModal.modal('hide');
            
            // Needs to wait for the event because the call to .modal('hide');
            // returns before the modal has actually been hidden
            return new Promise(resolve => {
                $(satModal).one('hidden.bs.modal', function() {
                    resolve();
                });
            });
        }
    }

    async function moveNext() {
        hide_alert();
        await waitForSatelliteModalClose();
        save_current_obs_state();
        btn_prev.disabled = false;
        current_obs_index = (current_obs_index + 1) % page_size;
        if(current_obs_index == 0) {
            current_page_num++;
            // If we are not at the last page and the page is not already in memory, load it
            if(current_page_num != total_pages_num && !pages[current_page_num+1]) {
                fetchObsHtml(current_page_num+1);
            }
            // Remove old previous page from memory, as we are moving forward
            let delete_page_num = get_page_num_to_clean_bwd(current_page_num);
            if(delete_page_num) {
                delete_page(delete_page_num);
            }
        } else if(current_obs_index == page_size -1 && !pages[current_page_num + 1]) {
            // If on the last observation of the page and the next page is not in memory...
            btn_next.disabled = true;
            loading_spinner.classList.remove('d-none');
        }
        // Disable 'btn_next' when on the last observation
        if((current_page_num - 1) * page_size + current_obs_index + 1 == total_items) {
            btn_next.disabled = true;
        }
        replaceContainer(current_obs_index);
        update_obs_num_display();
        set_copy_link_btn();
    }

    async function moveBack() {
        hide_alert();
        await waitForSatelliteModalClose();
        save_current_obs_state();
        btn_next.disabled = false;
        current_obs_index = current_obs_index - 1;
        if(current_obs_index == -1) {
            current_obs_index += page_size;  // e.g -1 + 25 = 24, which is the index of the last of the page
            current_page_num--;
            if(current_page_num > 1 && !pages[current_page_num - 1]) {  // Previous pages might have been removed from memory 
                fetchObsHtml(current_page_num - 1);
            }
            // Remove old next page from memory, as we are moving backwards
            let delete_page_num = get_page_num_to_clean_fwd(current_page_num);
            if(delete_page_num) {
                delete_page(delete_page_num);
            }
        } else if(current_obs_index == 0 && current_page_num > 1 && !pages[current_page_num - 1]) {
            // If on the first observation of the page and the previous page is not in memory...
            btn_prev.disabled = true;
            loading_spinner.classList.remove('d-none');
        }
        // Disable 'btn_prev' when on the first observation
        if(current_page_num == 1 & current_obs_index == 0) {
            btn_prev.disabled = true;
        }
        replaceContainer(current_obs_index);
        update_obs_num_display();
        set_copy_link_btn();
    }

    btn_next.addEventListener('click', moveNext);
    document.addEventListener('obs_vetted', () => {
        if(!btn_next.disabled && auto_advance_checkbox.checked) {
            moveNext();
        }
    });
    btn_prev.addEventListener('click', moveBack);

    window.addEventListener('keydown', function(event) {
        switch(event.key) {
        case 'a':
        case 'ArrowLeft':
            if (!btn_prev.disabled) {
                moveBack();
            }
            break;
        case 'd':
        case 'ArrowRight':
            if (!btn_next.disabled) {
                moveNext();
            }
            break;
        }
    });

    function replaceContainer() {
        loading_spinner.classList.add('d-none');
        container.innerHTML = pages[current_page_num.toString()][current_obs_index];
        document.dispatchEvent(obs_changed_event);
        $('#tab-waterfall-btn').tab('show');
        let img_tag = document.getElementById('waterfall-img');
        let waterfall_spinner = document.getElementById('waterfall-loading');
        if(img_tag) {
            waitForWaterfall(img_tag, () => {
                let waterfall_blob = waterfalls[`${current_page_num.toString()}-${current_obs_index.toString()}`];
                let img_src = URL.createObjectURL(waterfall_blob);
                img_tag.src = img_src;
                if(waterfall_spinner) {
                    waterfall_spinner.remove();
                }
            });
        }
    
        function waitForWaterfall(img_tag, callback) {
            if (waterfalls[`${current_page_num.toString()}-${current_obs_index.toString()}`]) {
                callback();
            } else {
                setTimeout(() => waitForWaterfall(img_tag, callback), 50); // Check again after 50ms
            }
        }
    }

    function get_ids_param(page_num) {
        // Implements paging and returns the IDs as comma-separated url parameter value 
        const startIdx = (page_num - 1) * page_size;
        const endIdx = startIdx + page_size;
        const slice = obs_ids.slice(startIdx, endIdx);
        return (slice.lenth > 1) ? slice.join(','): slice;
    }

    function fetchObsHtml(page_num) {
        const ids_param = get_ids_param(page_num);
        return fetch(`${query_url}?obs_ids=${ids_param}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error. Status: ${response.status}`);
                }
                return response.json();
            }).then(data => {
                pages[page_num] = data;
                // If the page is after the current
                //  or it is the first page and there are at least two observations
                if(page_num >= current_page_num) {
                    if(total_items > 1) {
                        btn_next.disabled = false;
                    }
                } else {
                    btn_prev.disabled = false;
                }
                preload_waterfall(data, page_num);
            });
    }

    fetchObsHtml(1).then(() => {
        replaceContainer();
        set_copy_link_btn();
    });

    let i = 2;
    while(i <= 1 + chunks_buffer_headstart) {
        fetchObsHtml(i);
        i++;
    }
});
