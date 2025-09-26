document.addEventListener('DOMContentLoaded', () => {
    const mapContainer = document.getElementById('map-container');
    const canvas = document.getElementById('track-canvas');
    const ctx = canvas.getContext('2d');
    const dashboardTbody = document.querySelector('#train-status-table tbody');

    let staticNetworkData = null;
    let minX, maxX, minY, maxY, scale, offsetX, offsetY;

    function calculateBoundsAndScale() {
        const coords = Object.values(staticNetworkData.nodes).map(n => n.coords);
        minX = Math.min(...coords.map(c => c[0]));
        maxX = Math.max(...coords.map(c => c[0]));
        minY = Math.min(...coords.map(c => c[1]));
        maxY = Math.max(...coords.map(c => c[1]));

        const padding = 20; // pixels
        const canvasWidth = mapContainer.clientWidth - padding * 2;
        const canvasHeight = mapContainer.clientHeight - padding * 2;
        
        const scaleX = canvasWidth / (maxX - minX);
        const scaleY = canvasHeight / (maxY - minY);
        scale = Math.min(scaleX, scaleY);
        
        const centerX = (minX + maxX) / 2;
        const centerY = (minY + maxY) / 2;
        
        offsetX = (mapContainer.clientWidth / 2) - (centerX * scale);
        offsetY = (mapContainer.clientHeight / 2) - (centerY * scale);
    }
    
    function transformCoords(lon, lat) {
        return {
            x: lon * scale + offsetX,
            y: lat * scale + offsetY
        };
    }

    async function initializeMap() {
        try {
            const response = await fetch('http://127.0.0.1:5000/api/network');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            staticNetworkData = await response.json();
            
            canvas.width = mapContainer.clientWidth;
            canvas.height = mapContainer.clientHeight;
            
            calculateBoundsAndScale();

            ctx.strokeStyle = '#4a5568';
            ctx.lineWidth = 2;
            staticNetworkData.edges.forEach(edge => {
                const [u, v] = edge;
                const startNode = staticNetworkData.nodes[u];
                const endNode = staticNetworkData.nodes[v];
                if (!startNode || !endNode) return;

                const start = transformCoords(startNode.coords[0], startNode.coords[1]);
                const end = transformCoords(endNode.coords[0], endNode.coords[1]);
                
                ctx.beginPath();
                ctx.moveTo(start.x, start.y);
                ctx.lineTo(end.x, end.y);
                ctx.stroke();
            });

            Object.entries(staticNetworkData.nodes).forEach(([name, data]) => {
                const pos = transformCoords(data.coords[0], data.coords[1]);

                const nodeDiv = document.createElement('div');
                nodeDiv.className = `node ${data.type}`;
                nodeDiv.style.left = `${pos.x}px`;
                nodeDiv.style.top = `${pos.y}px`;
                mapContainer.appendChild(nodeDiv);

                const labelDiv = document.createElement('div');
                labelDiv.className = 'node-label';
                labelDiv.textContent = name.replace(/_/g, " ");
                labelDiv.style.left = `${pos.x}px`;
                labelDiv.style.top = `${pos.y + 10}px`;
                mapContainer.appendChild(labelDiv);
            });
        } catch (error) {
            console.error("Failed to initialize map:", error);
            mapContainer.innerHTML = "<p style='color:red; text-align:center; padding: 2rem;'>Error: Could not load network data. Is the Python simulation server running?</p>";
        }
    }

    async function updateSimulationView() {
        if (!staticNetworkData) return;

        try {
            const response = await fetch('http://127.0.0.1:5000/api/state');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const state = await response.json();
            
            dashboardTbody.innerHTML = '';

            Object.values(state.trains).forEach(train => {
                let trainDiv = document.getElementById(train.id);
                if (!trainDiv) {
                    trainDiv = document.createElement('div');
                    trainDiv.id = train.id;
                    trainDiv.className = `train ${train.type}`;
                    trainDiv.textContent = train.id.split('_')[0].substring(0, 3);
                    mapContainer.appendChild(trainDiv);
                }

                if (train.current_node && train.next_node && staticNetworkData.nodes[train.current_node] && staticNetworkData.nodes[train.next_node]) {
                    const startNode = staticNetworkData.nodes[train.current_node];
                    const endNode = staticNetworkData.nodes[train.next_node];
                    const edgeDist = getEdgeDistance(train.current_node, train.next_node);
                    const progressRatio = edgeDist > 0 ? train.progress_km / edgeDist : 0;
                    
                    const startPos = transformCoords(startNode.coords[0], startNode.coords[1]);
                    const endPos = transformCoords(endNode.coords[0], endNode.coords[1]);

                    const x = startPos.x + (endPos.x - startPos.x) * progressRatio;
                    const y = startPos.y + (endPos.y - startPos.y) * progressRatio;
                    
                    trainDiv.style.left = `${x}px`;
                    trainDiv.style.top = `${y}px`;
                }

                const row = `<tr>
                    <td>${train.id.replace(/_/g, " ")}</td>
                    <td class="${train.type}">${train.type}</td>
                    <td>${train.current_node ? train.current_node.replace(/_/g, " ") : 'N/A'}</td>
                    <td>${train.next_node ? train.next_node.replace(/_/g, " ") : 'DEST'}</td>
                    <td>${train.speed_kmh.toFixed(0)} km/h</td>
                </tr>`;
                dashboardTbody.innerHTML += row;
            });
        } catch (error) {
            console.error("Failed to update view:", error);
        }
    }

    function getEdgeDistance(u, v) {
        const edge = staticNetworkData.edges.find(e => (e[0] === u && e[1] === v) || (e[0] === v && e[1] === u));
        return edge ? edge[2].distance_km : Infinity;
    }

    initializeMap();
    setInterval(updateSimulationView, 1000);
});