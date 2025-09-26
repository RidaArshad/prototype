// --- SETUP ---
const canvas = document.getElementById('track-canvas');
const ctx = canvas.getContext('2d');
const trainStatusTableBody = document.querySelector('#train-status-table tbody');

let networkData = {}; // To store the raw network data
let nodePositions = {}; // To store calculated {x, y} for each node
let trackLengths = {}; // To store track lengths in meters
let latestState = {}; // To store the latest state from the API

// --- INITIALIZATION ---

window.onload = async () => {
    // Set canvas size based on its container
    resizeCanvas();
    window.addEventListener('resize', () => {
        resizeCanvas();
        // Recalculate positions and redraw if the window size changes
        if (networkData.nodes) {
            calculateNodePositions();
            draw();
        }
    });

    // Fetch the static network layout once
    try {
        const response = await fetch('/api/network');
        networkData = await response.json();
        
        // Calculate and store positions for drawing
        calculateNodePositions();
        networkData.tracks.forEach(t => trackLengths[t.id] = t.length);

        // Start the main loop
        mainLoop();
    } catch (error) {
        console.error("Failed to initialize simulation:", error);
        ctx.fillStyle = 'red';
        ctx.font = '16px ' + getComputedStyle(document.body).fontFamily;
        ctx.fillText('Could not load network data. Is the backend running?', 50, 50);
    }
};

function resizeCanvas() {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
}

function calculateNodePositions() {
    // A more robust layout algorithm to space nodes out on the canvas
    const { nodes } = networkData;
    const padding = 60; // Increased padding for better spacing
    const viewWidth = canvas.clientWidth - padding * 2;
    const viewHeight = canvas.clientHeight - padding * 2;

    const columns = {};
    nodes.forEach(node => {
        const key = node.id.split('_')[1] || 'Terminus';
        if (!columns[key]) columns[key] = [];
        columns[key].push(node.id);
    });

    const sortedColumnKeys = Object.keys(columns).sort((a, b) => {
        if (a.includes('Entry')) return -1;
        if (b.includes('Entry')) return 1;
        if (a.includes('Exit')) return 1;
        if (b.includes('Exit')) return -1;
        return a.localeCompare(b, undefined, {numeric: true});
    });

    const xStep = sortedColumnKeys.length > 1 ? viewWidth / (sortedColumnKeys.length - 1) : viewWidth / 2;
    
    sortedColumnKeys.forEach((key, i) => {
        const colNodes = columns[key].sort();
        const yStep = viewHeight / (colNodes.length + 1);
        colNodes.forEach((nodeId, j) => {
            nodePositions[nodeId] = { 
                x: i * xStep + padding, 
                y: (j + 1) * yStep + padding 
            };
        });
    });
    console.log("Calculated Node Positions:", nodePositions); // For debugging
}

// --- MAIN LOOP ---

async function mainLoop() {
    try {
        const response = await fetch('/api/state');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        latestState = await response.json();

        draw(); // Redraw everything with new data
    } catch (error) {
        console.error("Error fetching state:", error);
    }
    setTimeout(mainLoop, 1000); // Repeat every second
}

// --- DRAWING FUNCTIONS ---

function draw() {
    if (!networkData.nodes) return;
    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw network components
    drawTracks();
    drawNodes();
    
    // Draw dynamic components
    if (latestState.trains) {
        drawTrains();
        updateDashboard();
    }
}

function drawTracks() {
    ctx.strokeStyle = '#666';
    ctx.lineWidth = 2;
    networkData.tracks.forEach(track => {
        const start = nodePositions[track.start_node];
        const end = nodePositions[track.end_node];
        if (start && end) {
            ctx.beginPath();
            ctx.moveTo(start.x, start.y);
            ctx.lineTo(end.x, end.y);
            ctx.stroke();
        }
    });
}

function drawNodes() {
    ctx.fillStyle = '#ccc';
    ctx.font = '10px ' + getComputedStyle(document.body).fontFamily;
    ctx.textAlign = 'center';

    networkData.nodes.forEach(node => {
        const pos = nodePositions[node.id];
        if (pos) {
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, 5, 0, 2 * Math.PI);
            ctx.fill();
            ctx.fillText(node.name, pos.x, pos.y - 12);
        }
    });
}

function drawTrains() {
    Object.values(latestState.trains).forEach(train => {
        if (!train.current_track_id) return; // Don't draw trains that aren't on a track

        const track = networkData.tracks.find(t => t.id === train.current_track_id);
        if (!track) {
            console.warn(`Train ${train.id} is on an unknown track ID: ${train.current_track_id}`);
            return;
        }

        const start = nodePositions[track.start_node];
        const end = nodePositions[track.end_node];
        if (!start || !end) {
            console.warn(`Could not find node positions for track ${track.id} (Nodes: ${track.start_node}, ${track.end_node})`);
            return;
        }

        const progress = train.progress_on_track_m / track.length;
        const x = start.x + (end.x - start.x) * progress;
        const y = start.y + (end.y - start.y) * progress;

        // Draw train circle
        ctx.fillStyle = getTrainColor(train.priority);
        ctx.beginPath();
        ctx.arc(x, y, 7, 0, 2 * Math.PI);
        ctx.fill();
        ctx.strokeStyle = 'black';
        ctx.lineWidth = 1;
        ctx.stroke();

        // Draw train ID
        ctx.fillStyle = 'white';
        ctx.font = 'bold 11px ' + getComputedStyle(document.body).fontFamily;
        ctx.fillText(train.id, x, y + 20);
    });
}

function updateDashboard() {
    trainStatusTableBody.innerHTML = ''; // Clear existing data
    Object.values(latestState.trains).forEach(train => {
        const speedKmh = (train.speed_mps * 3.6).toFixed(1);
        const trainType = train.id.split('_')[0];
        
        let distToNext = '-';
        if (train.current_track_id) {
            const trackLength = trackLengths[train.current_track_id];
            if (trackLength) {
                const remainingDistM = Math.max(0, trackLength - train.progress_on_track_m);
                distToNext = (remainingDistM / 1000).toFixed(2); // Convert to km
            }
        }

        const row = `
            <tr>
                <td>${train.id}</td>
                <td>${trainType}</td>
                <td>${train.status}</td>
                <td>${speedKmh}</td>
                <td>${distToNext}</td>
            </tr>`;
        trainStatusTableBody.innerHTML += row;
    });
}

// --- HELPER FUNCTIONS ---

function getTrainColor(priority) {
    if (priority === 1) return '#e06c75'; // Red for high priority
    if (priority === 2) return '#98c379'; // Green for medium
    return '#61afef'; // Blue for low
}

