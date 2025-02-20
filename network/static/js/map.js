/*global maplibregl*/

$(document).ready(function() {
    'use strict';

    var mapboxtoken = $('div#map').data('mapboxtoken');
    var stations = $('div#map').data('stations');

    maplibregl.accessToken = mapboxtoken;

    var map = new maplibregl.Map({
        container: 'map',
        style: 'mapbox://styles/pierros/cj8kftshl4zll2slbelhkndwo',
        zoom: 2,
        minZoom: 2,
        center: [10,29]
    });

    map.touchZoomRotate.disableRotation();
    map.dragRotate.disable();
    if (!('ontouchstart' in window)) {
        map.addControl(new maplibregl.NavigationControl());
    }

    map.on('load', function () {

        map.loadImage('/static/img/online.png', function(error, image) {
            map.addImage('online', image);
        });

        map.loadImage('/static/img/testing.png', function(error, image) {
            map.addImage('testing', image);
        });

        map.loadImage('/static/img/offline.png', function(error, image) {
            map.addImage('offline', image);
        });

        var connected_points = {
            'id': 'connected-points',
            'type': 'symbol',
            'source': {
                'type': 'geojson',
                'data': {
                    'type': 'FeatureCollection',
                    'features': []
                }
            },
            'layout': {
                'icon-image': 'online',
                'icon-size': 0.25,
                'icon-allow-overlap': true
            }
        };

        var testing_points = {
            'id': 'testing-points',
            'type': 'symbol',
            'source': {
                'type': 'geojson',
                'data': {
                    'type': 'FeatureCollection',
                    'features': []
                }
            },
            'layout': {
                'icon-image': 'testing',
                'icon-size': 0.25,
                'icon-allow-overlap': true
            }
        };

        $.ajax({
            url: stations
        }).done(function(data) {
            data.forEach(function(station) {

                if (station.testing){
                    create_station_point(testing_points, station);
                } else {
                    create_station_point(connected_points, station);
                }
            });

            // Add layers to map
            map.addLayer(testing_points);
            map.addLayer(connected_points);

            map.repaint = false;
        });
    });

    function create_station_point(array, station) {
        var key = `${station.lng}${station.lat}`;
        var index = array.source.data.features.findIndex(e => e.key === key);
        if (index > -1){
            array.source.data.features[index].properties.description += '</br><a href="/stations/' + station.id + '">' + station.id + ' - ' + station.name + '</a>';
        }
        array.source.data.features.push({
            'key': key,
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [
                    parseFloat(station.lng),
                    parseFloat(station.lat)]
            },
            'properties': {
                'description': '<a href="/stations/' + station.id + '">' + station.id + ' - ' + station.name + '</a>',
            }
        });
    }

    // Create a popup, but don't add it to the map yet.
    var popup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: true
    });

    map.on('mouseenter', 'connected-points', function(e) {
        // Change the cursor style as a UI indicator.
        map.getCanvas().style.cursor = 'pointer';

        // Populate the popup and set its coordinates
        // based on the feature found.
        popup.setLngLat(e.features[0].geometry.coordinates)
            .setHTML(e.features[0].properties.description)
            .addTo(map);
    });

    map.on('mouseenter','testing-points', function(e) {
        // Change the cursor style as a UI indicator.
        map.getCanvas().style.cursor = 'pointer';

        // Populate the popup and set its coordinates
        // based on the feature found.
        popup.setLngLat(e.features[0].geometry.coordinates)
            .setHTML(e.features[0].properties.description)
            .addTo(map);
    });

    // Resize map for Stations modal
    $('#MapModal').on('shown.bs.modal', function () {
        map.resize();
    });
});
