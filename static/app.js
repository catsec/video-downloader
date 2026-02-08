document.addEventListener('DOMContentLoaded', function() {
    var form = document.getElementById('downloadForm');
    var submitBtn = document.getElementById('submitBtn');
    var btnText = document.getElementById('btnText');
    var spinner = document.getElementById('spinner');
    var statusLog = document.getElementById('statusLog');
    var statusMessages = document.getElementById('statusMessages');
    var videoPlayerDiv = document.getElementById('videoPlayer');
    var videoElement = document.getElementById('videoElement');
    var videoSource = document.getElementById('videoSource');
    var downloadBtn = document.getElementById('downloadBtn');
    var videoUrlInput = document.getElementById('videoUrl');

    if (!form) {
        console.error('Form element not found');
        return;
    }

    var eventSource = null;
    var downloadComplete = false;
    var MAX_LOG_LINES = 5;

    function setLoading(loading) {
        submitBtn.disabled = loading;
        if (loading) {
            btnText.textContent = 'Processing...';
            spinner.classList.remove('hidden');
        } else {
            btnText.textContent = 'Download';
            spinner.classList.add('hidden');
        }
    }

    function updateButtonText(status) {
        if (status.indexOf('Downloading') !== -1) {
            btnText.textContent = 'Downloading...';
        } else if (status.indexOf('Converting') !== -1 || status.indexOf('encoding') !== -1) {
            btnText.textContent = 'Converting...';
        } else if (status.indexOf('Merging') !== -1) {
            btnText.textContent = 'Merging...';
        } else if (status.indexOf('Checking') !== -1 || status.indexOf('Validating') !== -1) {
            btnText.textContent = 'Processing...';
        }
    }

    function showLog() {
        if (statusLog) {
            statusLog.classList.remove('hidden');
        }
    }

    function hideLog() {
        if (statusLog) {
            statusLog.classList.add('hidden');
        }
    }

    function clearLog() {
        if (statusMessages) {
            statusMessages.innerHTML = '';
        }
    }

    function addLogLine(message, type) {
        type = type || 'info';
        if (!statusMessages) return;

        var line = document.createElement('div');
        line.className = 'log-line ' + type;
        line.textContent = message;
        statusMessages.appendChild(line);

        while (statusMessages.children.length > MAX_LOG_LINES) {
            statusMessages.removeChild(statusMessages.firstChild);
        }

        if (statusLog) {
            statusLog.scrollTop = statusLog.scrollHeight;
        }
    }

    function showVideoPlayer(downloadId, filename) {
        if (!videoPlayerDiv) return;

        var downloadUrl = '/api/download/' + downloadId;

        videoSource.src = downloadUrl;
        videoElement.load();

        downloadBtn.href = downloadUrl;
        downloadBtn.download = filename || 'video-' + downloadId + '.mp4';

        videoPlayerDiv.classList.remove('hidden');

        videoElement.addEventListener('loadeddata', function() {
            videoElement.play().catch(function(err) {
                // Auto-play may be blocked by browser
            });
        }, { once: true });
    }

    function hideVideoPlayer() {
        if (videoPlayerDiv) {
            videoPlayerDiv.classList.add('hidden');
        }
        if (videoElement) {
            videoElement.pause();
        }
        if (videoSource) {
            videoSource.src = '';
        }
        if (videoElement) {
            videoElement.load();
        }
    }

    form.addEventListener('submit', function(e) {
        e.preventDefault();

        var url = videoUrlInput.value.trim();

        if (!url) {
            showLog();
            addLogLine('Please enter a video URL', 'error');
            return;
        }

        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }

        downloadComplete = false;

        setLoading(true);
        hideVideoPlayer();
        clearLog();
        showLog();
        addLogLine('Starting download...');

        var encodedUrl = encodeURIComponent(url);
        var sseUrl = '/api/download/stream?url=' + encodedUrl;

        eventSource = new EventSource(sseUrl);

        eventSource.addEventListener('status', function(e) {
            try {
                var data = JSON.parse(e.data);
                addLogLine(data.status);
                updateButtonText(data.status);
            } catch (err) {
                console.error('Error parsing status:', err);
            }
        });

        eventSource.addEventListener('complete', function(e) {
            downloadComplete = true;

            try {
                var data = JSON.parse(e.data);

                if (eventSource) {
                    eventSource.close();
                    eventSource = null;
                }

                addLogLine('Ready! (' + data.platform + ')', 'success');
                showVideoPlayer(data.download_id, data.filename);
                setLoading(false);

                setTimeout(function() {
                    hideLog();
                }, 3000);
            } catch (err) {
                console.error('Error parsing complete:', err);
            }
        });

        eventSource.addEventListener('error', function(e) {
            if (e.data) {
                try {
                    var data = JSON.parse(e.data);
                    addLogLine('Error: ' + data.error, 'error');
                } catch (err) {
                    console.error('Error parsing error event:', err);
                }
                if (eventSource) {
                    eventSource.close();
                    eventSource = null;
                }
                setLoading(false);
            }
        });

        eventSource.onerror = function(e) {
            if (downloadComplete) {
                return;
            }

            if (!eventSource || eventSource.readyState === EventSource.CLOSED) {
                return;
            }

            addLogLine('Connection lost. Please try again.', 'error');
            eventSource.close();
            eventSource = null;
            setLoading(false);
        };
    });
});
