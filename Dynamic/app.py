from flask import Flask, jsonify
import networkx as nx
import time
import threading
from flask import render_template_string
import copy
import os

app = Flask(__name__)

SAFETY_MARGIN_METERS = 200

simulation_state = {
    'trains': {
        "Express_101": {"id": "Express_101", "position_km": 10.0, "speed_kmh": 90.0, "max_speed_kmh": 120, "braking_rate": 0.8, "priority": 1},
        "Local_202": {"id": "Local_202", "position_km": 15.0, "speed_kmh": 40.0, "max_speed_kmh": 80, "braking_rate": 0.8, "priority": 2},
        "Goods_303": {"id": "Goods_303", "position_km": 5.0, "speed_kmh": 30.0, "max_speed_kmh": 60, "braking_rate": 0.6, "priority": 3}
    },
    'occupied_tracks': []
}

state_lock = threading.Lock()

track_data = {
    'nodes': [
        ("Ballari Junction", {"type": "station"}), ("Signal_BLR_1", {"type": "signal"}),
        ("Siding_Entry", {"type": "junction"}), ("Toranagallu", {"type": "station"}),
        ("Signal_TOR_1", {"type": "signal"}), ("Kudligi", {"type": "station"}),
        ("Hosapete", {"type": "station"})
    ],
    'edges': [
        ("Ballari Junction", "Signal_BLR_1", {"distance_km": 10, "base_time_mins": 8}),
        ("Signal_BLR_1", "Toranagallu", {"distance_km": 15, "base_time_mins": 12}),
        ("Toranagallu", "Signal_TOR_1", {"distance_km": 5, "base_time_mins": 4}),
        ("Signal_TOR_1", "Kudligi", {"distance_km": 20, "base_time_mins": 15}),
        ("Toranagallu", "Hosapete", {"distance_km": 25, "base_time_mins": 20}),
        ("Ballari Junction", "Siding_Entry", {"distance_km": 12, "base_time_mins": 15}),
        ("Siding_Entry", "Toranagallu", {"distance_km": 12, "base_time_mins": 15}),
    ]
}

def create_railway_graph():
    G = nx.Graph()
    G.add_nodes_from(track_data['nodes'])
    G.add_edges_from(track_data['edges'])
    for u, v, data in G.edges(data=True):
        data['time_cost'] = data.get('base_time_mins', 20)
    return G

def find_optimal_path(graph, start_node, end_node):
    try:
        return nx.astar_path(graph, start_node, end_node, weight="time_cost")
    except nx.NetworkXNoPath:
        return None

def update_graph_with_traffic(graph, current_state):
    for u, v, data in graph.edges(data=True):
        cost = data.get('base_time_mins', 20)
        if (u, v) in current_state['occupied_tracks'] or (v, u) in current_state['occupied_tracks']:
            cost = 9999
        graph[u][v]['time_cost'] = cost

def calculate_braking_distance(speed_kmh, braking_rate=0.8):
    speed_mps = speed_kmh / 3.6
    return (speed_mps ** 2) / (2 * braking_rate)

def calculate_dynamic_speed_limit(following_train, train_ahead):
    braking_distance_ahead = calculate_braking_distance(train_ahead['speed_kmh'], train_ahead['braking_rate'])
    safe_point_meters = train_ahead['position_km'] * 1000 - braking_distance_ahead - SAFETY_MARGIN_METERS
    distance_to_safe_point = safe_point_meters - (following_train['position_km'] * 1000)
    
    if distance_to_safe_point <= 0:
        return 0
        
    safe_speed_mps = (2 * distance_to_safe_point * following_train['braking_rate']) ** 0.5
    safe_speed_kmh = safe_speed_mps * 3.6
    return min(safe_speed_kmh, following_train['max_speed_kmh'])

def simulation_loop():
    TICK_RATE_SECONDS = 1.0

    while True:
        with state_lock:
            sorted_trains = sorted(simulation_state['trains'].values(), key=lambda t: t['position_km'])

            # --- (Inside simulation_loop) ---
            for i, current_train in enumerate(sorted_trains):
                train_ahead = None
                if i + 1 < len(sorted_trains):
                    train_ahead = sorted_trains[i+1]

                # Default to max speed if the track is clear
                safe_speed_limit = current_train['max_speed_kmh'] 

                # If there's a train ahead, calculate a more restrictive speed limit
                if train_ahead:
                    safe_speed_limit = calculate_dynamic_speed_limit(current_train, train_ahead)

                # Now, apply acceleration or braking based on the final calculated limit
                if safe_speed_limit < current_train['speed_kmh']:
                    # Brake immediately for safety
                    current_train['speed_kmh'] = safe_speed_limit
                else:
                    # Accelerate gradually towards the speed limit
                    current_train['speed_kmh'] = min(safe_speed_limit, current_train['speed_kmh'] + 2)

            for train_id, train in simulation_state['trains'].items():
                distance_moved_km = train['speed_kmh'] * (TICK_RATE_SECONDS / 3600)
                train['position_km'] += distance_moved_km

            sorted_trains_after_update = sorted(simulation_state['trains'].values(), key=lambda t: t['position_km'])
            for i in range(len(sorted_trains_after_update) - 1):
                following_train = sorted_trains_after_update[i]
                train_ahead = sorted_trains_after_update[i+1]

                braking_dist_ahead_meters = calculate_braking_distance(train_ahead['speed_kmh'], train_ahead['braking_rate'])
                total_safety_bubble_meters = braking_dist_ahead_meters + SAFETY_MARGIN_METERS

                actual_distance_meters = (train_ahead['position_km'] - following_train['position_km']) * 1000

                if actual_distance_meters < total_safety_bubble_meters:
                    print(f"🔴 SAFETY ALERT: {following_train['id']} has breached the safety bubble of {train_ahead['id']}!")
                    print(f"   > Required Distance: {total_safety_bubble_meters:.2f}m, Actual Distance: {actual_distance_meters:.2f}m")
            display_simulation(simulation_state) # This will draw the updated state
        time.sleep(TICK_RATE_SECONDS)


def display_simulation(state):
    """
    Clears the terminal and draws a simple text-based representation of the simulation.
    """
    # Define the visual scale of our track
    TRACK_VISUAL_LENGTH_CHARS = 100  # How many characters wide the track is
    TOTAL_TRACK_KM = 50.0            # The total length of the railway in km this represents

    # --- Clear the screen ---
    # 'nt' is for Windows, 'posix' is for Mac/Linux
    os.system('cls' if os.name == 'nt' else 'clear')

    print("--- RAILWAY TRAFFIC CONTROL SIMULATION ---")
    print(f"Ballari Control Room - {time.strftime('%H:%M:%S')}")
    print("-" * TRACK_VISUAL_LENGTH_CHARS)

    # --- Prepare the track display ---
    track = ['.'] * TRACK_VISUAL_LENGTH_CHARS
    
    sorted_trains = sorted(state['trains'].values(), key=lambda t: t['position_km'])

    for train in sorted_trains:
        # --- Map the train's real position (km) to a character position on the visual track ---
        pos_ratio = train['position_km'] / TOTAL_TRACK_KM
        char_position = int(pos_ratio * TRACK_VISUAL_LENGTH_CHARS)
        
        # Ensure the character position is within the track bounds
        char_position = max(0, min(TRACK_VISUAL_LENGTH_CHARS - 1, char_position))
        
        # Use the first letter of the train ID as its icon (E, L, G)
        # If a spot is taken, show '*' to indicate close proximity
        if track[char_position] == '.':
            track[char_position] = train['id'][0]
        else:
            track[char_position] = '*'

    print(''.join(track))
    print("-" * TRACK_VISUAL_LENGTH_CHARS)

    # --- Print the detailed status of each train ---
    print("STATUS DASHBOARD:")
    for train in sorted_trains:
        print(f"  > {train['id']}: \t Pos: {train['position_km']:.2f} km | Speed: {train['speed_kmh']:.2f} km/h")

@app.route("/")
def home():
    return "<h1>Railway AI Simulation API (Live)</h1><p>Endpoints: /api/state, /api/path/start/end</p>"

@app.route("/api/state")
def get_current_state():
    with state_lock:
        return jsonify(copy.deepcopy(simulation_state))

@app.route("/api/path/<string:start_node>/<string:end_node>")
def get_path(start_node, end_node):
    with state_lock:
        current_state = copy.deepcopy(simulation_state)

    railway_map = create_railway_graph()
    update_graph_with_traffic(railway_map, current_state)
    path = find_optimal_path(railway_map, start_node, end_node)
    
    result = {
        "start_node": start_node,
        "end_node": end_node,
        "optimal_path": path,
        "blocked_tracks_at_moment": current_state["occupied_tracks"]
    }
    return jsonify(result)



@app.route("/viewer")
def viewer():
    # This HTML is now much more advanced, with CSS for styling and JS for rendering the state.
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Railway Simulation Viewer</title>
        <style>
            body { font-family: monospace, sans-serif; background-color: #1e1e1e; color: #d4d4d4; padding: 20px; }
            h1 { color: #569cd6; }
            .container { background-color: #252526; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
            #track { 
                font-size: 18px; 
                white-space: pre; 
                overflow-x: auto; 
                border: 1px solid #444;
                padding: 10px;
                letter-spacing: 2px;
            }
            .train { font-weight: bold; }
            .express { color: #c586c0; } /* Purple */
            .local { color: #4ec9b0; }   /* Teal */
            .goods { color: #dcdcaa; }   /* Yellow */
            .collision { color: #f44747; background-color: #ffcdd2; border-radius: 2px;} /* Red */

            #dashboard table { width: 100%; border-collapse: collapse; }
            #dashboard th, #dashboard td { padding: 8px; text-align: left; border-bottom: 1px solid #444; }
            #dashboard th { color: #9cdcfe; }
        </style>
    </head>
    <body>
        <h1>🚂 Railway Simulation Viewer</h1>
        <p>Live from Ballari Control Room - <span id="clock">{{ time_str }}</span></p>

        <div class="container">
            <h2>Live Track</h2>
            <div id="track">Loading track...</div>
        </div>

        <div class="container" id="dashboard">
            <h2>Status Dashboard</h2>
            <table>
                <thead><tr><th>ID</th><th>Position (km)</th><th>Speed (km/h)</th></tr></thead>
                <tbody id="train-data"></tbody>
            </table>
        </div>

        <script>
            // These constants must match the ones in your Python display_simulation function
            const TRACK_VISUAL_LENGTH_CHARS = 100;
            const TOTAL_TRACK_KM = 50.0;

            function updateClock() {
                const now = new Date();
                document.getElementById('clock').textContent = now.toLocaleTimeString();
            }

            async function updateSimulationView() {
                try {
                    const response = await fetch("/api/state");
                    const state = await response.json();
                    
                    // --- Render the Track ---
                    let track = Array(TRACK_VISUAL_LENGTH_CHARS).fill('·');
                    const sortedTrains = Object.values(state.trains).sort((a, b) => a.position_km - b.position_km);

                    for (const train of sortedTrains) {
                        const posRatio = train.position_km / TOTAL_TRACK_KM;
                        let charPosition = Math.floor(posRatio * TRACK_VISUAL_LENGTH_CHARS);
                        charPosition = Math.max(0, Math.min(TRACK_VISUAL_LENGTH_CHARS - 1, charPosition));

                        let trainClass = 'train';
                        if (train.id.includes('Express')) trainClass += ' express';
                        if (train.id.includes('Local')) trainClass += ' local';
                        if (train.id.includes('Goods')) trainClass += ' goods';

                        const trainIcon = `<span class="${trainClass}">${train.id[0]}</span>`;

                        if (track[charPosition] === '·') {
                            track[charPosition] = trainIcon;
                        } else {
                            track[charPosition] = `<span class="collision">*</span>`; // Collision/overlap icon
                        }
                    }
                    document.getElementById('track').innerHTML = track.join('');

                    // --- Render the Dashboard Table ---
                    const tableBody = document.getElementById('train-data');
                    tableBody.innerHTML = ''; // Clear previous data
                    for (const train of sortedTrains) {
                        const row = `<tr>
                            <td>${train.id}</td>
                            <td>${train.position_km.toFixed(2)}</td>
                            <td>${train.speed_kmh.toFixed(2)}</td>
                        </tr>`;
                        tableBody.innerHTML += row;
                    }

                } catch (error) {
                    console.error("Failed to fetch simulation state:", error);
                    document.getElementById('track').textContent = "Error connecting to simulation server.";
                }
            }
            
            // Initial load and then set intervals to update
                    updateClock();
                    updateSimulationView();
                    setInterval(updateClock, 1000);
                    setInterval(updateSimulationView, 1000);
        </script>
    </body>
    </html>
    """, time_str=time.strftime('%H:%M:%S')) # Pass current time for initial load

if __name__ == "__main__":
    simulation_thread = threading.Thread(target=simulation_loop, daemon=True)
    simulation_thread.start()
    app.run(debug=True, use_reloader=False)