import lhapi
client = lhapi.LighthouseApiClient()
#client._do_auth()
print(client.nodes().smartgroups().find('smart_groups_nodes_groups-1'))
