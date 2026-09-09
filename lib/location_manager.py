#!/usr/bin/env python3
"""
Location management module for GM tools
Handles location creation, connections, and descriptions
"""

import sys
from typing import Dict, List, Optional, Any
from pathlib import Path

# Add lib directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from entity_manager import EntityManager


class LocationManager(EntityManager):
    """Manage location operations. Inherits from EntityManager for common functionality."""

    def __init__(self, world_state_dir: str = None):
        super().__init__(world_state_dir)
        self.locations_file = "locations.json"

    def add_location(self, name: str, position: str) -> bool:
        """
        Add a new location
        Returns True on success, False on failure
        """
        # Validate name
        valid, error = self.validators.validate_name(name)
        if not valid:
            print(f"[ERROR] {error}")
            return False

        # Check if location already exists
        if self._entity_exists(self.locations_file, name):
            print(f"[ERROR] Location '{name}' already exists")
            return False

        # Create location data
        location_data = {
            'position': position,
            'connections': [],
            'description': '',
            'discovered': self.get_timestamp()
        }

        # Save to file
        if self._add_entity(self.locations_file, name, location_data):
            print(f"[SUCCESS] Added location: {name} ({position})")
            return True
        return False

    def connect_locations(self, from_loc: str, to_loc: str, path: str) -> bool:
        """
        Connect two locations bidirectionally
        """
        # Validate names
        for loc in [from_loc, to_loc]:
            valid, error = self.validators.validate_name(loc)
            if not valid:
                print(f"[ERROR] {error}")
                return False

        # Load locations
        locations = self._load_entities(self.locations_file)

        # Check both locations exist
        if from_loc not in locations:
            print(f"[ERROR] Location '{from_loc}' not found")
            return False
        if to_loc not in locations:
            print(f"[ERROR] Location '{to_loc}' not found")
            return False

        # Check if connection already exists
        existing_connections = [c['to'] for c in locations[from_loc].get('connections', [])]
        if to_loc in existing_connections:
            print(f"[ERROR] Connection already exists between '{from_loc}' and '{to_loc}'")
            return False

        # Add bidirectional connection
        if 'connections' not in locations[from_loc]:
            locations[from_loc]['connections'] = []
        if 'connections' not in locations[to_loc]:
            locations[to_loc]['connections'] = []

        locations[from_loc]['connections'].append({
            'to': to_loc,
            'path': path
        })
        locations[to_loc]['connections'].append({
            'to': from_loc,
            'path': path
        })

        if self._save_entities(self.locations_file, locations):
            print(f"[SUCCESS] Connected {from_loc} <-> {to_loc} via {path}")
            return True
        return False

    def set_description(self, name: str, description: str) -> bool:
        """
        Set or update location description
        """
        # Validate name
        valid, error = self.validators.validate_name(name)
        if not valid:
            print(f"[ERROR] {error}")
            return False

        # Check if location exists
        if not self._entity_exists(self.locations_file, name):
            print(f"[ERROR] Location '{name}' not found")
            return False

        # Update description
        if self._update_entity(self.locations_file, name, {'description': description}):
            print(f"[SUCCESS] Updated description for {name}")
            return True
        return False

    def get_location(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get location data
        """
        valid, error = self.validators.validate_name(name)
        if not valid:
            print(f"[ERROR] {error}")
            return None

        location = self._get_entity(self.locations_file, name)
        if not location:
            print(f"[ERROR] Location '{name}' not found")
            return None

        return location

    def list_locations(self) -> List[str]:
        """
        List all location names
        """
        locations = self._load_entities(self.locations_file)
        return list(locations.keys())

    def get_connections(self, name: str) -> List[Dict[str, str]]:
        """
        Get connections for a location
        """
        location = self.get_location(name)
        if location:
            return location.get('connections', [])
        return []

    def create_batch(self, locations_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create multiple locations in batch

        Args:
            locations_data: List of location dictionaries with name, description, position, etc.

        Returns:
            List of results for each location with success/error status
        """
        results = []
        locations = self._load_entities(self.locations_file)

        for loc_data in locations_data:
            result = {'name': loc_data.get('name', 'Unknown')}

            # Validate required fields
            if not loc_data.get('name'):
                result['success'] = False
                result['error'] = 'Missing location name'
                results.append(result)
                continue

            name = loc_data['name']

            # Check for duplicates
            if name in locations:
                result['success'] = False
                result['error'] = f'Location {name} already exists'
                results.append(result)
                continue

            # Create location entry
            location_entry = {
                'position': loc_data.get('position', 'unknown'),
                'description': loc_data.get('description', ''),
                'connections': [],
                'discovered': self.get_timestamp()
            }

            # Add source if provided
            if loc_data.get('source'):
                location_entry['source'] = loc_data['source']

            # Process connections if provided
            if loc_data.get('connections'):
                for conn_name in loc_data['connections']:
                    location_entry['connections'].append({
                        'to': conn_name,
                        'path': 'connected'
                    })

            # Add notes if provided
            if loc_data.get('notes'):
                location_entry['notes'] = loc_data['notes']

            # Add to locations dictionary (pending save)
            locations[name] = location_entry
            result['_pending'] = True
            results.append(result)

        # Save all locations at once, then mark success/failure
        pending = [r for r in results if r.get('_pending')]
        if pending:
            saved = self._save_entities(self.locations_file, locations)
            for result in pending:
                del result['_pending']
                if saved:
                    result['success'] = True
                else:
                    result['success'] = False
                    result['error'] = 'Failed to save to file'

        return results


def main():
    """CLI interface for location management"""
    import argparse
    import contextlib
    import io as _io
    import json

    from cli_output import wants_json, strip_json_flag, emit, emit_error

    json_mode = wants_json()

    parser = argparse.ArgumentParser(description='Location management')
    subparsers = parser.add_subparsers(dest='action', help='Action to perform')

    # Add location
    add_parser = subparsers.add_parser('add', help='Add new location')
    add_parser.add_argument('name', help='Location name')
    add_parser.add_argument('position', help='Relative position')

    # Connect locations
    connect_parser = subparsers.add_parser('connect', help='Connect two locations')
    connect_parser.add_argument('from_loc', help='From location')
    connect_parser.add_argument('to_loc', help='To location')
    connect_parser.add_argument('path', help='Path description')

    # Describe location
    describe_parser = subparsers.add_parser('describe', help='Set location description')
    describe_parser.add_argument('name', help='Location name')
    describe_parser.add_argument('description', help='Description text')

    # Get location
    get_parser = subparsers.add_parser('get', help='Get location info')
    get_parser.add_argument('name', help='Location name')

    # List locations
    subparsers.add_parser('list', help='List all locations')

    # Get connections
    connections_parser = subparsers.add_parser('connections', help='Get location connections')
    connections_parser.add_argument('name', help='Location name')

    args = parser.parse_args(strip_json_flag(sys.argv[1:]))

    if not args.action:
        parser.print_help()
        sys.exit(1)

    manager = LocationManager()

    def _quiet():
        """The manager prints [SUCCESS]/[ERROR] from inside its own logic; in JSON
        mode that text would precede the envelope and break json.loads."""
        return (contextlib.redirect_stdout(_io.StringIO()) if json_mode
                else contextlib.nullcontext())

    def _fail(message, status=1):
        """JSON mode gets the error envelope; human mode keeps the manager's own
        message and its bare exit status, byte for byte as before."""
        if json_mode:
            emit_error(message, json_mode)
        sys.exit(status)

    if args.action == 'add':
        with _quiet():
            added = manager.add_location(args.name, args.position)
        if not added:
            _fail(f"could not add location: {args.name}")
        emit({'name': args.name, 'position': args.position}, json_mode=json_mode)

    elif args.action == 'connect':
        with _quiet():
            connected = manager.connect_locations(args.from_loc, args.to_loc, args.path)
        if not connected:
            _fail(f"could not connect {args.from_loc} <-> {args.to_loc}")
        emit({'from': args.from_loc, 'to': args.to_loc, 'path': args.path},
             json_mode=json_mode)

    elif args.action == 'describe':
        with _quiet():
            described = manager.set_description(args.name, args.description)
        if not described:
            _fail(f"could not describe location: {args.name}")
        emit({'name': args.name, 'description': args.description}, json_mode=json_mode)

    elif args.action == 'get':
        with _quiet():
            location = manager.get_location(args.name)
        if not location:
            _fail(f"no such location: {args.name}")
        if json_mode:
            emit({args.name: location}, json_mode=True)
        else:
            print(json.dumps({args.name: location}, indent=2))

    elif args.action == 'list':
        locations = manager.list_locations()
        if json_mode:
            emit(locations, json_mode=True)
        elif locations:
            for loc in locations:
                print(f"  - {loc}")
        else:
            print("No locations found")

    elif args.action == 'connections':
        # get_connections() calls get_location(), which prints its [ERROR] to STDOUT
        # when the name is unknown — unquieted, that text lands ahead of the envelope.
        with _quiet():
            connections = manager.get_connections(args.name)
        if json_mode:
            # An unknown location yields [] here, indistinguishable from a known one
            # with no roads, and human mode calls neither a failure (it exits 0). The
            # flag changes the SHAPE of an answer, never its status, so this stays
            # ok: true. A caller that needs existence asks `get`, which reports
            # ok: false.
            emit(connections, json_mode=True)
        elif connections:
            print(json.dumps(connections, indent=2))
        else:
            print("No connections found")


if __name__ == "__main__":
    main()
