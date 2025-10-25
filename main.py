import requests
import heapq  # This is the library for the priority queue
import time
import math


# --- Helper Function 1: Get Relatedness ---
# This is our "compass" or "Haki". It tells us how
# close a word is to our final target.

def get_relatedness(node1, node2):
    """
    Asks the ConceptNet API for the relatedness score between two nodes.
    """
    try:
        # The /relatedness endpoint gives a score from 0.0 to 1.0+
        api_url = f"http://api.conceptnet.io/relatedness?node1={node1}&node2={node2}"
        response = requests.get(api_url)
        response.raise_for_status()  # Raises an error for bad responses (4xx, 5xx)

        data = response.json()

        # The score is in the 'value' field
        return data.get('value', 0.0)

    except requests.exceptions.RequestException as e:
        # print(f"  [API Error (Relatedness): {e}]")
        return 0.0  # On error, just assume 0 relatedness


# --- Helper Function 2: Get Neighbors ---
# This finds all connected concepts for a given node.

def get_neighbors(node_uri):
    """
    Gets all unique, Japanese neighbors for a given ConceptNet node URI.
    """
    neighbors = set()
    try:
        api_url = f"http://api.conceptnet.io{node_uri}"
        response = requests.get(api_url)
        response.raise_for_status()

        data = response.json()
        for edge in data.get('edges', []):
            start_node = edge['start'].get('@id')
            end_node = edge['end'].get('@id')
            if start_node.startswith(node_uri):
                neighbors.add(end_node)
            elif end_node.startswith(node_uri):
                neighbors.add(start_node)

    except requests.exceptions.RequestException as e:
        # print(f"  [API Error (Neighbors): {e}]")
        pass  # Silently fail on this node

    return neighbors

def get_max_relatedness(node1, node2):
    # Finds all the neighbors of node1 and returns one with the maximum relatedness score to node2
    neighbors = get_neighbors(node1)
    neighbors=list(neighbors)
    print(neighbors)
    max_related_neighbor=""
    max_relatedness = 0.0
    relatednesses=[]
    for neighbor in neighbors:
        if neighbor==node2:
            return neighbor
        relatedness = get_relatedness(node2, neighbor)
        if abs(relatedness) > max_relatedness:
            max_relatedness = abs(relatedness)
            max_related_neighbor = neighbor
        relatednesses.append((neighbor, relatedness))
    print(relatednesses)
    return max_related_neighbor

target="/c/en/capital_of_italy"
current="/c/en/rome"
while current!=target:
    current=get_max_relatedness(current,target)
    print(current)
    break