import requests
import time
from collections import deque
import threading
import json
import os

# --- Constants ---
CACHE_FILENAME = "conceptnet_cache.json"


# --- Rate Limiter ---
class RateLimiter:
    def __init__(self, requests_per_second):
        self.delay = 1.0 / requests_per_second
        self.last_request_time = 0
        self.lock = threading.Lock()

    def wait(self):
        """Waits until it's safe to make the next request."""
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_request_time

            if elapsed < self.delay:
                sleep_time = self.delay - elapsed
                # print(f"[RateLimiter] Sleeping for {sleep_time:.2f}s")
                time.sleep(sleep_time)

            self.last_request_time = time.monotonic()


# --- Pathfinder Class ---
class ConceptNetPathfinder:
    def __init__(self, cache_file=CACHE_FILENAME):
        self.cache_file = cache_file
        self.load_cache()  # Load cache on initialization
        self.rate_limiter = RateLimiter(requests_per_second=1)
        self.session = requests.Session()  # Use a session for connection pooling

    def load_cache(self):
        """Loads the node cache from a JSON file."""
        if os.path.exists(self.cache_file):
            print(f"[Cache] Loading cache from {self.cache_file}...")
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.node_cache = json.load(f)
                print(f"[Cache] Loaded {len(self.node_cache)} nodes from disk.")
            except json.JSONDecodeError:
                print(f"[Cache] Error: Cache file is corrupt. Starting with empty cache.")
                self.node_cache = {}
        else:
            print(f"[Cache] No cache file found. Starting with empty cache.")
            self.node_cache = {}

    def save_cache(self):
        """Saves the node cache to a JSON file."""
        print(f"\n[Cache] Saving {len(self.node_cache)} nodes to {self.cache_file}...")
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.node_cache, f, indent=2)
            print(f"[Cache] Save complete.")
        except IOError as e:
            print(f"[Cache] Error: Could not save cache: {e}")

    # --- THIS FUNCTION IS FIXED ---
    def get_edges(self, node_uri):
        """
        Gets all edges for a node, using the cache if available.
        This function now returns the relation type and the neighbor.
        """
        # 1. Check the cache first
        if node_uri in self.node_cache:
            # print(f"  [Cache HIT] Found {node_uri}")
            return self.node_cache[node_uri]

        # 2. If not in cache, make the API call
        # print(f"  [Cache MISS] Fetching {node_uri}...")
        self.rate_limiter.wait()

        edges = []
        try:
            api_url = f"http://api.conceptnet.io{node_uri}"
            response = self.session.get(api_url, timeout=10)
            response.raise_for_status()

            data = response.json()
            for edge in data.get('edges', []):
                rel_label = edge['rel'].get('label', 'relatedTo')
                start_node = edge['start'].get('@id')
                end_node = edge['end'].get('@id')

                if start_node == node_uri:
                    neighbor_node = end_node
                    edges.append((rel_label, neighbor_node, "-->"))
                elif end_node == node_uri:
                    neighbor_node = start_node
                    edges.append((rel_label, neighbor_node, "<--"))

            # 3. Store the result in the cache
            # --- FIX ---
            # These two lines MUST be INSIDE the 'try' block.
            # We only cache a result if the API call was successful.
            self.node_cache[node_uri] = edges
            return edges

        except requests.exceptions.RequestException as e:
            print(f"  [API Error] Failed to get neighbors for {node_uri}: {e}")
            # On error, return an empty list BUT DO NOT CACHE IT.
            return []

        # --- BUG WAS HERE ---
        # The cache line was outside the try/except block,
        # causing failed API calls to be cached as empty lists [].

    def reconstruct_and_print_path(self, start_node, end_node, path_fwd, path_bwd):
        """
        Combines the two paths from the bi-directional search and prints them.
        """
        print(f"  {start_node}")

        # 1. Print the forward path (start -> meet)
        current = start_node
        for (rel, next_node, direction) in path_fwd:
            arrow = " --[ {} ]--> ".format(rel) if direction == "-->" else " <--[ {} ]-- ".format(rel)
            print(f"   {arrow} {next_node}")
            current = next_node

        # 2. Print the backward path (meet -> end)
        path_bwd_nodes = [end_node] + [p[1] for p in path_bwd]
        path_bwd_nodes.reverse()  # Now [meet, node_before_meet, ..., end]
        reversed_rels = list(reversed(path_bwd))

        for i in range(len(reversed_rels)):
            rel, node_in_path, dir_from_end = reversed_rels[i]

            flipped_dir = "<--" if dir_from_end == "-->" else "-->"
            arrow = " --[ {} ]--> ".format(rel) if flipped_dir == "-->" else " <--[ {} ]-- ".format(rel)
            next_node_in_chain = path_bwd_nodes[i + 1]
            print(f"   {arrow} {next_node_in_chain}")
            current = next_node_in_chain

    def find_path(self, start_node, end_node):
        """
        Performs a Bi-directional Breadth-First Search (BFS).
        """
        if start_node == end_node:
            print("Start and end nodes are the same.")
            return

        print(f"Searching for path:\n  FROM: {start_node}\n  TO:   {end_node}\n")

        queue_fwd = deque([(start_node, [])])  # (node, path_list)
        paths_fwd = {start_node: []}
        queue_bwd = deque([(end_node, [])])  # (node, path_list)
        paths_bwd = {end_node: []}

        start_time = time.time()
        nodes_processed = 0

        try:
            while queue_fwd and queue_bwd:

                # --- 1. Expand Forward Layer ---
                if queue_fwd:
                    current_fwd, path_fwd = queue_fwd.popleft()
                    nodes_processed += 1

                    if len(path_fwd) > 10:  # Pruning
                        continue

                    if nodes_processed % 50 == 0:
                        print(
                            f"[Status] Processed: {nodes_processed}. Queues (f/b): {len(queue_fwd)}/{len(queue_bwd)}. "
                            f"Depth (f/b): {len(path_fwd)}/{len(queue_bwd[-1][1]) if queue_bwd else 0}. "
                            f"Time: {time.time() - start_time:.1f}s")

                    edges = self.get_edges(current_fwd)
                    for rel, neighbor, direction in edges:
                        if neighbor in paths_bwd:
                            print(f"\n--- 🥳 Path Found! (Intersection at {neighbor}) ---")
                            print(f"Processed {nodes_processed} nodes in {time.time() - start_time:.2f} seconds.")
                            new_path_fwd = path_fwd + [(rel, neighbor, direction)]
                            path_bwd = paths_bwd[neighbor]
                            self.reconstruct_and_print_path(start_node, end_node, new_path_fwd, path_bwd)
                            return

                        if neighbor not in paths_fwd:
                            new_path_fwd = path_fwd + [(rel, neighbor, direction)]
                            paths_fwd[neighbor] = new_path_fwd
                            queue_fwd.append((neighbor, new_path_fwd))

                # --- 2. Expand Backward Layer ---
                if queue_bwd:
                    current_bwd, path_bwd = queue_bwd.popleft()
                    nodes_processed += 1

                    if len(path_bwd) > 10:  # Pruning
                        continue

                    edges = self.get_edges(current_bwd)
                    for rel, neighbor, direction in edges:
                        if neighbor in paths_fwd:
                            print(f"\n--- 🥳 Path Found! (Intersection at {neighbor}) ---")
                            print(f"Processed {nodes_processed} nodes in {time.time() - start_time:.2f} seconds.")
                            path_fwd = paths_fwd[neighbor]
                            new_path_bwd = path_bwd + [(rel, neighbor, direction)]
                            self.reconstruct_and_print_path(start_node, end_node, path_fwd, new_path_bwd)
                            return

                        if neighbor not in paths_bwd:
                            new_path_bwd = path_bwd + [(rel, neighbor, direction)]
                            paths_bwd[neighbor] = new_path_bwd
                            queue_bwd.append((neighbor, new_path_bwd))

            print(f"\n--- 😥 Path Not Found ---")
            print(f"Explored {nodes_processed} nodes in {time.time() - start_time:.2f} seconds.")

        finally:
            self.save_cache()


# --- Main Execution ---
if __name__ == "__main__":
    start_2 = "/c/en/banana"
    target_2 = "/c/en/fruit"

    start_4 = "/c/en/puppy"
    target_4 = "/c/en/loyal"

    # --- Run the Search ---
    pathfinder = ConceptNetPathfinder()

    pathfinder.find_path(start_2, target_2)
    print("\n" + "=" * 40 + "\n")

    pathfinder.find_path(start_4, target_4)
    print("\n" + "=" * 40 + "\n")

    # --- Long Haul Tests ---
    # pathfinder.find_path("/c/en/toaster", "/c/en/justice")
    # print("\n" + "=" * 40 + "\n")

    # ... (rest of your tests) ...
    pathfinder.find_path("/c/en/toaster", "/c/en/justice")
    print("\n" + "=" * 40 + "\n")

    pathfinder.find_path("/c/en/photosynthesis", "/c/en/sonnet")
    print("\n" + "=" * 40 + "\n")

    pathfinder.find_path("/c/en/zeus", "/c/en/microprocessor")
    print("\n" + "=" * 40 + "\n")

    pathfinder.find_path("/c/en/sushi", "/c/en/black_hole")
    print("\n" + "=" * 40 + "\n")

    pathfinder.find_path("/c/en/hippocampus", "/c/en/stock_market")
    print("\n" + "=" * 40 + "\n")

    pathfinder.find_path("/c/en/hammer", "/c/en/globalization")
    print("\n" + "=" * 40 + "\n")

    pathfinder.find_path("/c/en/platypus", "/c/en/nostalgia")
    print("\n" + "=" * 40 + "\n")

    pathfinder.find_path("/c/en/hair", "/c/en/bear")
    pathfinder.find_path("/c/es/naranja", "/c/en/death_star")
    pathfinder.find_path("/c/es/infinity", "/c/en/zero")