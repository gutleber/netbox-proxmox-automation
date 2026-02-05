#!/usr/bin/env python3

import os, sys, re
import time
import argparse
import yaml
import json
import getpass
import paramiko
import pynetbox
import proxmoxer
import urllib3

from helpers.netbox_proxmox_cluster import NetBoxProxmoxCluster
#from helpers.netbox_proxmox_api import NetBoxProxmoxAPIHelper
from helpers.netbox_objects import __netbox_make_slug, NetBox, NetBoxSites, NetBoxManufacturers, NetBoxPlatforms, NetBoxTags, NetBoxDeviceRoles, NetBoxDeviceTypes, NetBoxDeviceTypesInterfaceTemplates, NetBoxDevices, NetBoxDevicesInterfaces, NetBoxDeviceInterface, NetBoxDeviceBridgeInterface, NetBoxObjectInterfaceMacAddressMapping, NetBoxClusterTypes, NetBoxClusters, NetBoxClusterGroups, NetBoxVirtualMachines, NetBoxVirtualMachineInterface, NetBoxIPAddresses

from proxmoxer import ProxmoxAPI, ResourceException

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_arguments():
    # Initialize the parser
    parser = argparse.ArgumentParser(description="Import Proxmox Cluster (optional) and Nodes Configurations")

    parser.add_argument("--config", required=True, help="YAML file containing the configuration")
    parser.add_argument("--debug", action='store_true', default=False, help="Enable debug (verbose) output")
    parser.add_argument("--simulate", action='store_true', default=False, help="Simulate device collection.  DO NOT USE.  INTERNAL ONLY!")

    # Parse the arguments
    args = parser.parse_args()

    # Return the parsed arguments
    return args


def convert_proxmox_interface_type_to_netbox(proxmox_type: str):
    """Convert Proxmox interface type to NetBox interface type"""
    interface_type_mapping = {
        '1gbase-t': '1000base-t',
        '10gbase-t': '10gbase-t',
        '100base-tx': '100base-tx',
        'bridge': 'virtual',
        'vlan': 'virtual',
        'bond': 'lag',
        'other': 'other'
    }
    return interface_type_mapping.get(proxmox_type, 'other')


def get_proxmox_node_vmbr_network_interface_mapping(proxmox_api_config: dict, proxmox_node: str, network_interface: str):
    proxmox_vmbrX_network_interface_mapping = {}

    try:
        proxmox = ProxmoxAPI(
            proxmox_api_config['api_host'],
            port=proxmox_api_config['api_port'],
            user=proxmox_api_config['api_user'],
            token_name=proxmox_api_config['api_token_id'],
            token_value=proxmox_api_config['api_token_secret'],
            verify_ssl=False
        )

        proxmox_node_network_settings = proxmox.nodes(proxmox_node).network.get()

        proxmox_vmbrX_interface_mapping = list(filter(lambda d: 'bridge_ports' in d and d['bridge_ports'] == network_interface, proxmox_node_network_settings))

        if proxmox_vmbrX_interface_mapping:
            if not network_interface in proxmox_vmbrX_network_interface_mapping:
                proxmox_vmbrX_network_interface_mapping[network_interface] = []

            proxmox_vmbrX_network_interface_mapping[network_interface] = proxmox_vmbrX_interface_mapping[0]['iface']
        
        return proxmox_vmbrX_network_interface_mapping
    except ResourceException as e:
        print("Proxmox Resource Exception encountered", e, dir(e), e.status_code, e.status_message, e.errors)
        if e.errors:
            if 'vmid' in e.errors:
                print("  - for vmid:", e.errors['vmid'])

    return {}


def main():
    default_proxmox_cluster_type = 'Proxmox'
    discovered_proxmox_nodes_information = {}

    args = get_arguments()

    DEBUG = args.debug
    SIMULATE = args.simulate

    if DEBUG:
        print("ARGS", args, args.config)

    try:
        with open(args.config, 'r') as cfg_f:
            app_config = yaml.safe_load(cfg_f)

        if DEBUG:
            print(f"CONFIGURATION DATA {app_config}")
    except yaml.YAMLError as exc:
        print(exc)

    nb_url = f"{app_config['netbox_api_config']['api_proto']}://{app_config['netbox_api_config']['api_host']}:{str(app_config['netbox_api_config']['api_port'])}/"
    nb_options = {}

    if 'verify_ssl' in app_config['netbox_api_config']:
        nb_options['verify_ssl'] = app_config['netbox_api_config']['verify_ssl']
    else:
        nb_options['verify_ssl'] = False

    if 'branch' in app_config['netbox']:
        branch_name = app_config['netbox']['branch']

        nb_options['branch'] = branch_name

        branch_timeout = 0
        if 'branch_timeout' in app_config['netbox']:
            branch_timeout = int(app_config['netbox']['branch_timeout'])

        nb_options['branch_timeout'] = branch_timeout
    
    nb_options['debug'] = DEBUG
    nb_options['simulate'] = SIMULATE
    
    nb_pxmx_cluster = NetBoxProxmoxCluster(app_config, nb_options)

    if not 'site' in app_config['netbox']:
        netbox_site = "netbox-proxmox-automation Default Site"
    else:
        netbox_site = app_config['netbox']['site']

    if not SIMULATE:
        # Collect Proxmox node login information
        nb_pxmx_cluster.generate_proxmox_node_creds_configuration()
        proxmox_nodes_connection_info = nb_pxmx_cluster.proxmox_nodes_connection_info

        # discover nodes base system information
        nb_pxmx_cluster.get_proxmox_nodes_system_information()
        nb_pxmx_cluster.get_proxmox_nodes_network_interfaces()    
    else:
        print("*** IN SIMULATE MODE ***")
        nb_pxmx_cluster.simulate_get_proxmox_nodes_system_information()
        nb_pxmx_cluster.simulate_get_proxmox_nodes_network_interfaces()
        nb_pxmx_cluster.discovered_proxmox_nodes_information = nb_pxmx_cluster.proxmox_nodes

    discovered_proxmox_nodes_information = nb_pxmx_cluster.discovered_proxmox_nodes_information

    if DEBUG:
        print(f"DISCOVERED: {discovered_proxmox_nodes_information}")

    try:
        netbox_site_id = dict(NetBoxSites(nb_url, app_config['netbox_api_config']['api_token'], nb_options, {'name': netbox_site, 'slug': __netbox_make_slug(netbox_site), 'status': 'active'}).obj)['id']
    except pynetbox.RequestError as e:
        raise ValueError(e, e.error)

    # create cluster type and cluster in NetBox
    try:
        if 'cluster_role' in app_config['netbox']:
            proxmox_cluster_type = app_config['netbox']['cluster_role']
        else:
            proxmox_cluster_type = default_proxmox_cluster_type

        netbox_cluster_type_id = dict(NetBoxClusterTypes(nb_url, app_config['netbox_api_config']['api_token'], nb_options, {'name': proxmox_cluster_type, 'slug': __netbox_make_slug(proxmox_cluster_type)}).obj)['id']
    except pynetbox.RequestError as e:
        raise ValueError(e, e.error)        

    try:
        if 'cluster_group' in app_config['netbox']:
            cluster_group = app_config['netbox']['cluster_group']
        else:
            cluster_group = netbox_site

        netbox_cluster_group_id = dict(NetBoxClusterGroups(nb_url, app_config['netbox_api_config']['api_token'], nb_options, {'name': cluster_group, 'slug': __netbox_make_slug(cluster_group)}).obj)['id']
    except pynetbox.RequestError as e:
        raise ValueError(e, e.error)        

    try:
        netbox_cluster_id = dict(NetBoxClusters(nb_url, app_config['netbox_api_config']['api_token'], nb_options, {'name': nb_pxmx_cluster.proxmox_cluster_name, 'type': netbox_cluster_type_id, 'group': netbox_cluster_group_id, 'status': 'active'}).obj)['id']
    except pynetbox.RequestError as e:
        raise ValueError(e, e.error)        

    collected_netbox_device_type_ids = {}
    collected_netbox_interface_ids = {}

    for proxmox_node in discovered_proxmox_nodes_information:
        # Create Manufacturer in NetBox
        try:
            manufacturer_name = discovered_proxmox_nodes_information[proxmox_node]['system']['manufacturer']
            netbox_manufacturer_id = dict(NetBoxManufacturers(nb_url, app_config['netbox_api_config']['api_token'], nb_options, {'name': manufacturer_name, 'slug': __netbox_make_slug(manufacturer_name)}).obj)['id']
        except pynetbox.RequestError as e:
            raise ValueError(e, e.error)

        # Create Platform in NetBox
        if not 'version' in nb_pxmx_cluster.proxmox_nodes[proxmox_node]:
            raise ValueError(f"Missing Proxmox version information for {proxmox_node}")
        
        try:
            proxmox_version = nb_pxmx_cluster.proxmox_nodes[proxmox_node]['version']
            netbox_platform_id = dict(NetBoxPlatforms(nb_url, app_config['netbox_api_config']['api_token'], nb_options, {'name': proxmox_version, 'slug': __netbox_make_slug(proxmox_version)}).obj)['id']
        except pynetbox.RequestError as e:
            raise ValueError(e, e.error)        

        # Create NetBox Device Role
        try:
            device_role_name = app_config['netbox']['device_role']
            netbox_device_role_id = dict(NetBoxDeviceRoles(nb_url, app_config['netbox_api_config']['api_token'], nb_options, {'name': device_role_name, 'slug': __netbox_make_slug(device_role_name), 'vm_role': False}).obj)['id']
        except pynetbox.RequestError as e:
            raise ValueError(e, e.error)

        # Create Device Type in NetBox
        try:
            device_model = nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['model']
            netbox_device_type_id = dict(NetBoxDeviceTypes(nb_url, app_config['netbox_api_config']['api_token'], nb_options, {'manufacturer': netbox_manufacturer_id, 'model': device_model, 'slug': __netbox_make_slug(device_model), 'u_height': 1}).obj)['id']
            collected_netbox_device_type_ids[proxmox_node] = netbox_device_type_id
            print(f"CDT: {collected_netbox_device_type_ids}")
        except pynetbox.RequestError as e:
            raise ValueError(e, e.error)

        # Create Interfaces for Device Type in NetBox
        if DEBUG:
            print(f"We found these network interfaces for {proxmox_node}: {discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces']}")
            print()

        for network_interface in discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces']:
            if not proxmox_node in collected_netbox_interface_ids:
                collected_netbox_interface_ids[proxmox_node] = {}

            if not network_interface in collected_netbox_interface_ids[proxmox_node]:
                collected_netbox_interface_ids[proxmox_node][network_interface] = {}

            if network_interface.startswith('vmbr'):
                continue

            if DEBUG:
                print(f"Looking at network interface {network_interface} on {proxmox_node}")
                print()

            try:
                network_interface_type = nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]['type']

                if not proxmox_node in collected_netbox_device_type_ids:
                    NetBoxDeviceTypesInterfaceTemplates(nb_url, app_config['netbox_api_config']['api_token'], nb_options, {'device_type': collected_netbox_device_type_ids[proxmox_node], 'name': network_interface, 'type': network_interface_type, 'enabled': False})
            except pynetbox.RequestError as e:
                raise ValueError(e, e.error)

        # Create Device in NetBox
        try:
            device_serial = None

            if 'serial_number' in nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']:
                nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['serial'] = nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system'].pop('serial_number')

            system_info = nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']

            device_serial = system_info.get('serial')

            # If no serial or empty string, use a generated one or skip
            if not device_serial or device_serial.strip() == '':
                if DEBUG:
                    print(f"Warning: No serial found for {proxmox_node}, creating device without serial")

            device_payload = {
                'name': proxmox_node,
                'role': netbox_device_role_id,
                'device_type': collected_netbox_device_type_ids[proxmox_node],
                'site': netbox_site_id,
                'platform': netbox_platform_id,
                'cluster': netbox_cluster_id,
                'status': 'active'
            }

            # Only add serial number if it exists
            if device_serial:
                device_payload['serial'] = device_serial

            netbox_device_id = dict(NetBoxDevices(nb_url, app_config['netbox_api_config']['api_token'], nb_options, device_payload).obj)['id']
        except pynetbox.RequestError as e:
            raise ValueError(e, e.error)

        if not netbox_device_id:
            raise ValueError(f"NetBox missing device id for {proxmox_node}, device type id {netbox_device_type_id}")

        # Create device interfaces in NetBox
        if DEBUG:
            print("Adding device interfaces to NetBox")
            print()

        for network_interface in nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces']:
            if 'bridge_ports' in nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]:
                continue

            if DEBUG:
                print(f"+ Going to try and create network interface {network_interface} for device {netbox_device_id} ({proxmox_node}) in NetBox")

            interface_payload = {
                'device': netbox_device_id,
                'name': network_interface,
                'type': convert_proxmox_interface_type_to_netbox(nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]['type']),
                'enabled': nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]['enabled']
            }

            if DEBUG:
                print("  Interface payload", interface_payload)
                print()

            netbox_network_interface_id = dict(NetBoxDeviceInterface(nb_url, app_config['netbox_api_config']['api_token'], nb_options, interface_payload).obj)['id']
            collected_netbox_interface_ids[proxmox_node][network_interface] = netbox_network_interface_id

            if DEBUG:
                print("Collected NetBox Interface IDs", collected_netbox_interface_ids)
                print()

        # Create device (bridge) interfaces in NetBox
        if DEBUG:
            print("Adding device (bridge) interfaces to NetBox")
            print()

        for network_interface in nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces']:
            if 'bridge_ports' in nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]:
                if DEBUG:
                    print(f"+ Going to try and create network (bridge) interface {network_interface} for device {netbox_device_id} ({proxmox_node}) in NetBox")
                    print()

                interface_payload = {
                    'device': netbox_device_id,
                    'name': network_interface,
                    'type': nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]['type'],
                    'bridge': collected_netbox_interface_ids[proxmox_node][nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]['bridge_ports']],
                    'enabled': nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]['enabled']
                }

                if DEBUG:
                    print("  Bridge interface payload", interface_payload)
                    print()

                netbox_network_interface_id = dict(NetBoxDeviceInterface(nb_url, app_config['netbox_api_config']['api_token'], nb_options, interface_payload).obj)['id']
                collected_netbox_interface_ids[proxmox_node][network_interface] = netbox_network_interface_id

                if DEBUG:
                    print("  Collected NetBox (bridge) interface ids", collected_netbox_interface_ids)
                    print()

        # Now assign IP addresses amd MAC addresses to interfaces in NetBox
        if DEBUG:
            print("Assigning IP addresses and MAC addresses to device interfaces")
            print()

        for network_interface in nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces']:
            if network_interface in collected_netbox_interface_ids[proxmox_node]:
                nb_nw_if_id = collected_netbox_interface_ids[proxmox_node][network_interface]

                if 'ipv4address' in nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]:
                    nb_ipv4_address = nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]['ipv4address']

                    if DEBUG:
                        print(f"Attempting to assign (v4) IP {nb_ipv4_address} to {network_interface} on {proxmox_node}")
                        print()

                    nb_assign_ip_address_payload = {
                        'address': nb_ipv4_address,
                        'status': 'active',
                        'assigned_object_type': 'dcim.interface',
                        'assigned_object_id': str(nb_nw_if_id)
                    }

                    try:
                        NetBoxIPAddresses(nb_url, app_config['netbox_api_config']['api_token'], nb_options, nb_assign_ip_address_payload, 'address')
                    except pynetbox.RequestError as e:
                        raise ValueError(e, e.error)

                if 'ipv6address' in nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]:
                    nb_ipv6_address = nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]['ipv6address']

                    if DEBUG:
                        print(f"Attempting to assign (v6) IP {nb_ipv6_address} to {network_interface} on {proxmox_node}")
                        print()
                        
                    nb_assign_ip_address_payload = {
                        'address': nb_ipv6_address,
                        'status': 'active',
                        'assigned_object_type': 'dcim.interface',
                        'assigned_object_id': str(nb_nw_if_id)
                    }

                    try:
                        NetBoxIPAddresses(nb_url, app_config['netbox_api_config']['api_token'], nb_options, nb_assign_ip_address_payload, 'address')
                    except pynetbox.RequestError as e:
                        raise ValueError(e, e.error)
                    
                if 'mac' in nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]:
                    nb_mac_address = nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]['mac']

                    if DEBUG:
                        print(f"Attempting to assign MAC address {nb_mac_address} to {network_interface} on {proxmox_node}")
                        print()
                        
                    nb_assign_mac_address_payload = {
                        'mac': nb_mac_address,
                        'enabled': nb_pxmx_cluster.discovered_proxmox_nodes_information[proxmox_node]['system']['network_interfaces'][network_interface]['enabled']
                    }

                    try:
                        NetBoxObjectInterfaceMacAddressMapping(nb_url, app_config['netbox_api_config']['api_token'], nb_options, 'dcim.interface', netbox_device_id, network_interface, nb_assign_mac_address_payload)
                    except pynetbox.RequestError as e:
                        raise ValueError(e, e.error)


if __name__ == "__main__":
    main()
